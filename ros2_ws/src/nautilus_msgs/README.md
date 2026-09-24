# nautilus_msgs

Custom interfaces for the Nautilus stack. Everything that crosses a package boundary and is not covered by `sensor_msgs` / `geometry_msgs` / `mavros_msgs` lives here.

## Rules

- One message per file, `CamelCase.msg`, in `msg/`.
- Add the new file to `rosidl_generate_interfaces()` in `CMakeLists.txt`, and any new dependency to both `CMakeLists.txt` and `package.xml`.
- Prefer `std_msgs/Header` on anything that is sampled from the world.

## Current interfaces

| Interface | Topic | Status |
|---|---|---|
| `ArmCommand.msg` | `/arm/command` | **placeholder** — see open decision #4 |
