from __future__ import annotations

from pathlib import Path

from services.audio_service import AudioService
from services.battery_manager import BatteryManager
from services.command_dispatcher import CommandDispatcher
from services.display_service import DisplayService
from services.esp32_bridge import ESP32Bridge
from services.hardware_discovery import HardwareDiscovery
from services.health_monitor import HealthMonitor
from services.logger import get_recent_logs, setup_logger
from services.sensor_manager import SensorManager
from services.server_client import ServerClient
from services.state_machine import RobotState, StateMachine
from services.video_service import VideoService


class RobotCore:
    def __init__(self, config: dict, base_path: Path) -> None:
        self.config = config
        self.base_path = base_path
        self.logger = setup_logger(base_path)
        self.hardware = {}
        self.state_machine = StateMachine()
        self.discovery = HardwareDiscovery(config=config, logger=self.logger)
        self.esp32_bridge: ESP32Bridge | None = None
        self.video_service: VideoService | None = None
        self.display_service: DisplayService | None = None
        self.audio_service: AudioService | None = None
        self.battery_manager = BatteryManager(self.logger)
        self.sensor_manager = SensorManager(self.logger)
        self.server_client = ServerClient(config=config["server"], device_config=config["device"], logger=self.logger)
        self.command_dispatcher: CommandDispatcher | None = None
        self.health_monitor = HealthMonitor(self.logger)

    def initialize(self) -> None:
        self.state_machine.set_state(RobotState.BOOTING, reason="startup")
        self.hardware = self.discovery.run_full_discovery()

        self.esp32_bridge = ESP32Bridge(self.config["serial"], self.logger)
        esp32_status = self.esp32_bridge.connect()
        self.hardware["esp32"] = esp32_status
        self.state_machine.update_esp32(esp32_status.get("connected", False))

        self.video_service = VideoService(self.config["video"], self.logger, self.base_path, self.hardware["camera"])
        self.display_service = DisplayService(self.config["display"], self.logger, self.base_path, self.hardware["display"])
        self.audio_service = AudioService(
            self.config["audio"],
            self.logger,
            self.base_path,
            self.hardware["audio_input"],
            self.hardware["audio_output"],
        )

        self.command_dispatcher = CommandDispatcher(
            logger=self.logger,
            state_machine=self.state_machine,
            esp32_bridge=self.esp32_bridge,
            video_service=self.video_service,
            display_service=self.display_service,
            audio_service=self.audio_service,
            server_client=self.server_client,
        )

        battery_status = self.battery_manager.get_status()
        sensor_status = self.sensor_manager.get_status()
        self.state_machine.update_battery(battery_status)
        self.state_machine.update_obstacle(sensor_status["obstacle"])
        self.state_machine.set_state(RobotState.IDLE, reason="startup_complete")

        self.logger.info("Robot core initialized.")

    def refresh_status(self) -> None:
        if self.esp32_bridge:
            self.hardware["esp32"] = self.esp32_bridge.get_status()
            self.state_machine.update_esp32(self.hardware["esp32"].get("connected", False))
        if self.video_service:
            self.hardware["camera"] = self.video_service.get_status()
        if self.display_service:
            self.hardware["display"] = self.display_service.check_display()
        if self.audio_service:
            self.hardware["audio_input"] = self.audio_service.check_input()
            self.hardware["audio_output"] = self.audio_service.check_output()

    def build_status(self) -> dict:
        self.refresh_status()
        battery_status = self.battery_manager.get_status()
        sensor_status = self.sensor_manager.get_status()
        self.state_machine.update_battery(battery_status)
        self.state_machine.update_obstacle(sensor_status["obstacle"])
        server_status = self.server_client.get_status()
        health = self.health_monitor.build_report(
            hardware=self.hardware,
            battery=battery_status,
            sensors=sensor_status,
            state=self.state_machine.get_state(),
        )
        return {
            "device": self.config["device"],
            "state_machine": self.state_machine.get_state(),
            "safety": self.state_machine.get_safety_report(),
            "hardware": self.hardware,
            "battery": battery_status,
            "sensors": sensor_status,
            "server": server_status,
            "health": health,
            "logs": get_recent_logs(),
            "web": self.config["web"],
        }
