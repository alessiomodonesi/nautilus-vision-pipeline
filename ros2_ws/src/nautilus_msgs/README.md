# nautilus_msgs

Pacchetto ROS 2 contenente le definizioni di interfacce e messaggi custom per lo stack software del veicolo sottomarino **Nautilus**.

Centralizza tutti i messaggi che attraversano i confini tra pacchetti e che non sono coperti dalle definizioni standard di ROS 2 (`sensor_msgs`, `geometry_msgs`, `vision_msgs`, `std_msgs`).

---

## 1. Struttura del Pacchetto

```text
nautilus_msgs/
├── CMakeLists.txt
├── package.xml
├── README.md
└── msg/
    └── ArmCommand.msg              # Comando di controllo per il braccio manipolatore
```

---

## 2. Messaggi Definiti

### `ArmCommand.msg`

Definisce il protocollo di comando tra i nodi di decisione di alto livello (percezione e pianificazione) e il firmware del controllore del braccio robotico:

```text
std_msgs/Header header

# Numeri identificativi dei giunti secondo protocollo firmware (1, 2, 3)
uint8[] joint_numbers

# Numero di step da compiere per ciascun giunto
int32[] steps

# Direzione di rotazione ('F' per avanti, 'R' per indietro) - una per giunto
string[] directions

# Velocità massima di attuazione (step al secondo)
uint32[] max_steps_per_second

# Se true, cancella la coda dei comandi pendenti
bool clear_queue

# Flag per comando pinza (triggerato a fronte)
bool has_gripper_command
bool gripper_open
```

| Campo | Tipo | Descrizione |
| :--- | :--- | :--- |
| `header` | `std_msgs/Header` | Timestamp e frame di riferimento del comando |
| `joint_numbers` | `uint8[]` | Array degli ID dei giunti bersaglio |
| `steps` | `int32[]` | Passi da eseguire per ciascun giunto specificato |
| `directions` | `string[]` | Senso di rotazione (`"F"` = forward, `"R"` = reverse) |
| `max_steps_per_second` | `uint32[]` | Profilo di velocità massima |
| `clear_queue` | `bool` | Abilita l'arresto immediato o lo svuotamento della coda di movimento |
| `has_gripper_command` | `bool` | `true` se il messaggio include un'azione per l'end-effector |
| `gripper_open` | `bool` | `true` per aprire la pinza, `false` per serrarla |

---

## 3. Regole per l'Aggiunta di Nuove Interfacce

1. **Naming**: Un solo messaggio per file, denominato in `CamelCase.msg` all'interno della cartella `msg/`.
2. **Inclusione nel Build System**: Registrare ogni nuovo file `.msg` all'interno di `rosidl_generate_interfaces()` in `CMakeLists.txt`.
3. **Dipendenze**: Dichiarare le dipendenze da altri pacchetti di messaggi (es. `std_msgs`) sia in `CMakeLists.txt` sia in `package.xml`.
4. **Header**: Includere sempre `std_msgs/Header` nei messaggi che rappresentano dati campionati nel mondo fisico o comandi temporizzati.

---

## 4. Uso nei Pacchetti Client

### In Nodi Python (`rclpy`)

```python
from nautilus_msgs.msg import ArmCommand

msg = ArmCommand()
msg.header.stamp = self.get_clock().now().to_msg()
msg.joint_numbers = [1, 2]
msg.steps = [100, -200]
msg.directions = ['F', 'R']
msg.max_steps_per_second = [500, 500]
msg.has_gripper_command = True
msg.gripper_open = False
self.cmd_publisher.publish(msg)
```

### In Nodi C++ (`rclcpp`)

```cpp
#include "nautilus_msgs/msg/arm_command.hpp"

auto msg = nautilus_msgs::msg::ArmCommand();
msg.header.stamp = this->now();
msg.has_gripper_command = true;
msg.gripper_open = true;
publisher_->publish(msg);
```
