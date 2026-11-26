from __future__ import annotations


class CommandDispatcher:
    def __init__(self, logger, state_machine, esp32_bridge, video_service, display_service, audio_service, server_client) -> None:
        self.logger = logger
        self.state_machine = state_machine
        self.esp32_bridge = esp32_bridge
        self.video_service = video_service
        self.display_service = display_service
        self.audio_service = audio_service
        self.server_client = server_client

    def _handle_motion(self, command: str) -> dict:
        safety = self.state_machine.get_safety_report()
        if not safety["safe_to_move"]:
            return {"ok": False, "status": "error", "reason": "unsafe_to_move", "blockers": safety["blockers"]}

        result = self.esp32_bridge.send_command(command)
        if not result.get("ok"):
            stop_result = self.esp32_bridge.stop()
            if not stop_result.get("ok"):
                self.logger.critical("Motion command %s failed and emergency stop also failed.", command)
            else:
                self.logger.warning("Motion command %s failed. Stop command was sent.", command)
            return result

        self.state_machine.set_state("MOVING", reason=command)
        return result

    def forward(self) -> dict:
        return self._handle_motion("forward")

    def backward(self) -> dict:
        return self._handle_motion("backward")

    def left(self) -> dict:
        return self._handle_motion("left")

    def right(self) -> dict:
        return self._handle_motion("right")

    def stop(self) -> dict:
        result = self.esp32_bridge.stop()
        if result.get("ok"):
            self.state_machine.set_state("IDLE", reason="stop")
        return result

    def status(self) -> dict:
        return self.esp32_bridge.status()

    def snapshot(self) -> dict:
        self.state_machine.set_state("VIDEO_ACTIVE", reason="snapshot_requested")
        result = self.video_service.snapshot()
        self.state_machine.set_state("IDLE", reason="snapshot_complete")
        return result

    def display_face(self, face_name: str) -> dict:
        return self.display_service.show_face(face_name)

    def audio_test(self) -> dict:
        return self.audio_service.run_audio_test()

    def heartbeat(self) -> dict:
        return self.server_client.send_heartbeat()
