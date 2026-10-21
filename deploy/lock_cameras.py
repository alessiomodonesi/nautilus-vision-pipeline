#!/usr/bin/env python3
"""Lock fotometrico delle Pi Camera v3 per la pipeline stereo Nautilus."""

import os
import sys
import time
import yaml
import rclpy

from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from rcl_interfaces.srv import SetParameters
from rcl_interfaces.msg import Parameter, ParameterValue, ParameterType


# parametri che possono essere cambiati a runtime via set_parameters.
LOCKABLE_KEYS = {
    'AeEnable',
    'AwbEnable',
    'ExposureTime',
    'ColourGains',
    'AfMode',
    'LensPosition',
}

# namespace -> chiave nel yaml
CAMERA_YAML_KEYS = {
    'lx': '/stereo/lx/camera',
    'rx': '/stereo/rx/camera',
}


def load_lock_params(config_path):
    """Estrae i parametri lockabili da camera_params.yaml"""
    with open(config_path, 'r') as f:
        cfg = yaml.safe_load(f)

    lock_params = {}
    for ns, yaml_key in CAMERA_YAML_KEYS.items():
        section = cfg.get(yaml_key, {}).get('ros__parameters', {})
        filtered = {k: v for k, v in section.items() if k in LOCKABLE_KEYS}
        if not filtered:
            raise ValueError(
                f"no lockable parameters found under {yaml_key} in {config_path}"
            )
        lock_params[ns] = filtered
    return lock_params


def to_param(name, value):
    p = Parameter()
    p.name = name
    if isinstance(value, bool):
        p.value = ParameterValue(
            type=ParameterType.PARAMETER_BOOL, bool_value=value)
    elif isinstance(value, int):
        p.value = ParameterValue(
            type=ParameterType.PARAMETER_INTEGER, integer_value=value)
    elif isinstance(value, float):
        p.value = ParameterValue(
            type=ParameterType.PARAMETER_DOUBLE, double_value=value)
    elif isinstance(value, list):
        p.value = ParameterValue(
            type=ParameterType.PARAMETER_DOUBLE_ARRAY,
            double_array_value=[float(v) for v in value])
    else:
        raise TypeError(f"unsupported parameter type for {name}: {type(value)}")
    return p


def wait_for_service(client, timeout_s=30.0):
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        if client.service_is_ready():
            return True
        time.sleep(0.2)
    return False


def main() -> int:
    rclpy.init()
    node = Node("lock_cameras")

    try:
        # risolve il percorso del yaml tramite ament index
        pkg_share = get_package_share_directory('nautilus_camera')
        config_path = os.path.join(pkg_share, 'config', 'camera_params.yaml')

        try:
            lock_params = load_lock_params(config_path)
        except (OSError, ValueError, yaml.YAMLError) as e:
            print(f"[ERROR] cannot load {config_path}: {e}", file=sys.stderr)
            return 1

        for ns, params in lock_params.items():
            service_name = f"/stereo/{ns}/camera/set_parameters"
            client = node.create_client(SetParameters, service_name)

            print(f"Waiting for {service_name} ...", flush=True)
            if not wait_for_service(client):
                print(f"[ERROR] Service {service_name} not available after 30s",
                      file=sys.stderr)
                return 1

            req = SetParameters.Request()
            req.parameters = [to_param(k, v) for k, v in params.items()]

            future = client.call_async(req)
            rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)

            result = future.result()
            if result is None:
                print(f"[ERROR] Timeout setting params on /stereo/{ns}/camera",
                      file=sys.stderr)
                return 1

            rejected = [
                (r.reason, params_req.name)
                for r, params_req in zip(result.results, req.parameters)
                if not r.successful
            ]
            if rejected:
                for reason, name in rejected:
                    print(f"[WARN] /stereo/{ns}/camera: {name} -> {reason}",
                          file=sys.stderr)
            else:
                print(f"[OK] Locked /stereo/{ns}/camera", flush=True)

        print("Lock completed on both cameras.")
        return 0

    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
    