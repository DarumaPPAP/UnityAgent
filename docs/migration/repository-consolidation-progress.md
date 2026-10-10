# Repository Consolidation Progress

| Phase | Verified result | PR / merge |
|---|---|---|
| P0 Agent | Complete | #173 / 007dbc66365a8c2ca26fa12cbc89d5b544d7339a |
| P0 Hub | Complete | #93 / 83dcd6e7a2cba94e5bc0b4975579252da1d5e69a |
| P1 Agent | Canonical Green, Squash Merge | #175 / 0138030ac5b54ed45e8c5b0892f4170f48290184 |
| P2 Hub | Hub/Artist/Branch CI Green, Squash Merge | #94 / ccd6a21dee753c60211c1aa947f5220366cd7229 |
| P3 Agent | Hub pin and Release/Artist transition prepared; local validation recorded below | chore/repository-consolidation-p3 |
| P4 Hub | Artist/compatibility/docs move in progress; merge after P3 | chore/repository-consolidation-p4 |
| P5–P6 Agent | src/wheel/caller migration in isolated worktree | chore/repository-consolidation-p5 |
| P7 Hub | CI foundation prepared in isolated worktree; integrate after P4 | chore/repository-consolidation-p7 |
| P8 | Pending final layout and audit | — |

Source Lock now pins Hub merged full SHA ccd6a21dee753c60211c1aa947f5220366cd7229, Hub/Tools/export_snapshot.py, Hub/Registry and Hub/SubAgents. Artist CLI remains src/UnityArtist.Cli until the producer move. Release resolves exact allowlisted source paths from the same lock; old/new Artist layouts are prepared BEFORE producer migration. Mixed Catalog layouts, wrong repository/full SHA/identity and unknown CLI project remain rejected. New source-layout tests RED→GREEN, actual Development/Pinned Snapshot both read-only no_op.

P0 Inventory stays immutable historical evidence. Execution-file blocker resolved via Agent #174. Unity Editor/License/Player/Visual/device remain BLOCKED_NOT_RUN. Next: P3 CI Green/Squash Merge, Hub Artist move and final Agent re-pin. Confirm GitHub reality before resuming.
