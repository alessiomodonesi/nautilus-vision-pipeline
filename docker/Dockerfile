FROM ros:jazzy

# Installazione dei pacchetti base, dipendenze CV e tool di sistema (rimossi MoveIt/Controllers)
RUN apt-get update && apt-get install -y \
    ros-jazzy-ros-base \
    ros-jazzy-cv-bridge \
    ros-jazzy-vision-msgs \
    ros-jazzy-rmw-cyclonedds-cpp \
    chrony \
    v4l-utils \
    tmux \
    git \
    python3-pip \
    python3-opencv \
    && rm -rf /var/lib/apt/lists/*

# Configurazione di chrony per la sincronizzazione del tempo (Pi -> Jetson)
# Da completare con il file chrony.conf appropriato in fase di deploy

# Installa PyTorch CPU, OpenVINO e Ultralytics ignorando i pacchetti Debian
RUN pip3 install --no-cache-dir --default-timeout=1000 --break-system-packages \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip3 install --no-cache-dir --default-timeout=1000 --break-system-packages \
    openvino ultralytics numpy==1.26.4 setuptools

# Copia eventuali requirements aggiuntivi (ad es. per l'algoritmo di enhancement)
COPY ./ros2_ws/src/nautilus_perception/enhancement/requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

# Configurazione automatica dell'ambiente e di CycloneDDS al login
RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc
RUN echo "export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp" >> /root/.bashrc
RUN echo "source /ros2_ws/install/setup.bash" >> /root/.bashrc

WORKDIR /ros2_ws