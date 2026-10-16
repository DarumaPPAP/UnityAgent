#!/usr/bin/env python3
"""Structural PR quality checks. No external access, shell execution, or semantic QA."""
import argparse
import json
import re
import sys
from pathlib import Path

TITLES = {"feature":"機能追加：","fix":"不具合修正：","performance":"性能改善：",
          "visual":"表示変更：","qa":"テスト整備：","infrastructure":"基盤変更：",
          "maintenance":"保守："}
EVIDENCE = {"performance","visual","security","migration","platform"}
STATES = {"passed","failed","not_observed","blocked_not_run"}
HEADINGS = ("概要・変更目的","主な変更内容","検証結果・Evidence",
            "未検証・既知のリスク","関連Issue・PR・影響範囲")
PLACEHOLDER = re.compile(r"\b(?:TODO|TBD|FIXME|CHANGEME)\b|記入してください|ここに入力|ここに記載",re.I)

def strip_fences(body):
    lines=[]; active=""; count=0
    for line in body.splitlines():
        match=re.match(r"^ {0,3}([\x60]{3,}|~{3,})(.*)$",line)
        if match:
            token=match.group(1)
            if not active:
                active=token[0];count=len(token);lines.append("");continue
            if token[0]==active and len(token)>=count and not match.group(2).strip():
                active="";count=0;lines.append("");continue
        lines.append("" if active else line)
    return "\n".join(lines)

def validate(title,body):
    errors=[];warnings=[]
    def fail(code,msg): errors.append((code,msg))
    def warn(code,msg): warnings.append((code,msg))
    text=strip_fences(body)
    def marker(label,required):
        found=re.findall(r"<!--\s*"+re.escape(label)+r":\s*([^<>]*?)\s*-->",text,re.I)
        if len(found)>1 or (required and not found): fail("MARKER",label+" は1つ必要")
        return found[0].strip() if len(found)==1 else None
    kind=marker("pr-type",True)
    raw=marker("evidence",True)
    status_raw=marker("evidence-status",False)
    if kind not in TITLES: fail("TYPE","主分類は7種類から1つ")
    else:
        prefix=TITLES[kind]
        suffix=title[len(prefix):].strip() if title.startswith(prefix) else ""
        if len(suffix)<6 or "\n" in title or PLACEHOLDER.search(suffix):
            fail("TITLE","日本語タイトル形式が不正: "+prefix)
    evidence=set()
    if raw is not None and raw!="none":
        values=[v.strip() for v in raw.split(",")]
        if any(v not in EVIDENCE for v in values) or len(values)!=len(set(values)):
            fail("MARKER","evidenceの値が不正・重複")
        evidence=set(values)&EVIDENCE
    states={}
    if status_raw and status_raw!="none":
        for part in status_raw.split(","):
            bits=[v.strip() for v in part.split("=")]
            if len(bits)!=2 or bits[0] not in EVIDENCE or bits[1] not in STATES or bits[0] in states:
                fail("MARKER","evidence-statusの形式が不正");continue
            states[bits[0]]=bits[1]
    if status_raw=="none" and evidence: fail("MARKER","evidence指定に対してstatusがnone")
    if set(states)-evidence: fail("MARKER","未宣言Evidenceのstatus")
    if evidence and status_raw is None: warn("EVIDENCE","Evidenceの観測状態を記載")
    for name in sorted(evidence-set(states)):warn("EVIDENCE",name+"のstatusが未記載")
    sections={}
    heads=list(re.finditer(r"^##[ \t]+(.+?)[ \t]*$",text,re.M))
    for index,head in enumerate(heads):
        name=head.group(1).strip()
        if name in sections:fail("HEADING","見出し重複: "+name)
        sections[name]=text[head.end():heads[index+1].start() if index+1<len(heads) else len(text)]
    for name in HEADINGS:
        if name not in sections:fail("HEADING","必須見出し不足: "+name);continue
        paragraph=re.sub(r"<!--.*?-->","",sections[name],flags=re.S).strip()
        if not paragraph or PLACEHOLDER.search(paragraph):fail("BODY","未記入: "+name)
    if kind=="performance" and "performance" not in evidence:warn("EVIDENCE","性能改善にはperformanceを追加")
    if kind=="visual" and "visual" not in evidence:warn("EVIDENCE","表示変更にはvisualを追加")
    criteria={
        "performance":("性能比較",("Before","After","計測条件","測定回数","Commit SHA")),
        "visual":("Visual比較",("Before","After")),
        "security":("Security検証",("脅威","拒否テスト")),
        "migration":("Migration・Rollback",("互換","Rollback")),
        "platform":("Platform検証",("Platform","検証状態")),
    }
    for name in sorted(evidence):
        heading,tokens=criteria[name];part=sections.get(heading,"")
        missing=not part or any(t not in part for t in tokens)
        if name=="performance" and ("未計測" in part or "未算出" in part):missing=True
        if name=="visual" and not re.search(r"!\[[^\]]*\]\(https://[^)\s]+\)|https://[^)\s]+\.(?:mp4|mov|webm)\b",part):missing=True
        if missing:
            (fail if states.get(name)=="passed" else warn)("EVIDENCE",name+"の根拠不足。状態="+states.get(name,"未指定"))
    if states.get("platform") in ("blocked_not_run","not_observed") and re.search(
        r"(?:実機|Target Device)[^\n。]{0,24}(?:PASS|成功|検証済み)",text,re.I):
        fail("FALSE-PASS","実機未観測なのに実機成功と主張")
    return errors,warnings

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--event",type=Path);p.add_argument("--title")
    p.add_argument("--body-file",type=Path);p.add_argument("--json",action="store_true",dest="json_output")
    a=p.parse_args()
    if a.event:
        payload=json.loads(a.event.read_text(encoding="utf-8"))
        pr=payload.get("pull_request")
        if not isinstance(pr,dict):p.error("pull_request event required")
        title,body=pr.get("title") or "",pr.get("body") or ""
    elif a.title is not None and a.body_file: title,body=a.title,a.body_file.read_text(encoding="utf-8")
    else:p.error("specify --event or --title and --body-file")
    errors,warnings=validate(title,body)
    if a.json_output:
        print(json.dumps({"ok":not errors,"errors":errors,"warnings":warnings},ensure_ascii=False))
    else:
        for level,group in (("error",errors),("warning",warnings)):
            for code,msg in group:
                value=(code+": "+msg).replace("%","%25").replace("\r","%0D").replace("\n","%0A")
                print("::"+level+"::"+value)
        print("PR品質: errors="+str(len(errors))+" warnings="+str(len(warnings)))
    return 1 if errors else 0

if __name__=="__main__":
    sys.exit(main())
