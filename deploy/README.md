# config/

Shared runtime configuration.

| File | What it does | How it is used |
|---|---|---|
| `cyclonedds.xml` | Static peer discovery + WiFi-friendly fragment sizes | `export CYCLONEDDS_URI=file://$PWD/config/cyclonedds.xml` on every host |
| `qos_overrides.yaml` | Sensor-data QoS for images/lidar, reliable QoS for commands | passed as `--params-file` / in a launch file's `parameters:` |

Every host must also share the same `ROS_DOMAIN_ID` and the same `RMW_IMPLEMENTATION` (`rmw_cyclonedds_cpp`). See `docs/network.md`.
