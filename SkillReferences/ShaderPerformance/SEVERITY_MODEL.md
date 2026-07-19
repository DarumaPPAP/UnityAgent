# Shader Severity Model

`Priority = Impact × Frequency × Confidence × Reach - Risk`

Score each factor 1–5.

- Impact: negligible to frame-budget bottleneck
- Frequency: rare debug path to full-screen/many-instance/multi-overdraw
- Confidence: speculation to measured Before/After
- Reach: one shader to project-wide
- Risk: low to render-order/temporal/build-breaking

Severity:

- Critical: frame failure, missing Player variant, severe stall
- High: sustained major frame-budget impact
- Medium: conditional but clear opportunity
- Low: maintainability or small improvement
- Info: measurement/compiler-dependent candidate

Do not assign Critical or High without evidence and explicit conditions.
