# GPU Architecture Matrix

This document describes tendencies; target-device measurement wins.

| Concern | Desktop discrete | Mobile / tile-based | Console / fixed platform |
|---|---|---|---|
| Bandwidth | high but not free | critical for power/heat | optimize from target counters |
| Branches | coherent branches may win | check register/tile impact | fixed wave/compiler behavior |
| 16-bit | generation dependent | often useful for bandwidth/registers | verify compiler/ISA |
| Register pressure | occupancy/spill thresholds | occupancy/power/spill | establish target thresholds |
| Overdraw | transparent is expensive | blending and external-memory traffic are critical | resolution/bandwidth dependent |
| Intermediate RT | bandwidth cost | load/store especially expensive | evaluate whole frame |
| Early depth | important | include TBR/TBDR behavior | verify per pass |
| Small triangles | quad inefficiency | bin/raster inefficiency | inspect scene distribution |

Do not transfer desktop conclusions directly to Switch, console or mobile. Compare compiler reports and GPU captures for the actual target.
