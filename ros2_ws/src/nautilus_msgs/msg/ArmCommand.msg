std_msgs/Header header

# Motor numbers are the firmware protocol joint numbers (1, 2, 3).
uint8[] joint_numbers
int32[] steps
string[] directions       # F or R, one entry per joint_numbers entry
uint32[] max_steps_per_second

# A command with clear_queue=true contains no movement to enqueue.
bool clear_queue

# Gripper commands are edge-triggered by the producer. When false, no
# gripper action is requested by this message.
bool has_gripper_command
bool gripper_open