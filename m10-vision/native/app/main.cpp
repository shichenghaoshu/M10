#include "m10_core.hpp"
#include <iostream>

int main() {
  m10::MockMotorDriver motor; motor.initialize();
  m10::BehaviorMachine behavior; behavior.request(m10::State::SEARCH_PET);
  m10::SimpleTracker tracker;
  auto tracks = tracker.update({{15,"cat",0.91F,{220,120,420,420}}}, 640, 480);
  auto motion = behavior.update(tracks.front(), true, true, motor.healthy(), true);
  const int speed = motion == m10::Motion::STOP ? 0 : 25;
  motor.send({1,motion,speed,speed,motion == m10::Motion::STOP ? 0 : 250});
  std::cout << "state=" << m10::to_string(behavior.state()) << " track_id=" << tracks.front().track_id
            << " motion=" << m10::to_string(motion) << "\n" << m10::encode_motor_command(motor.history().front());
  behavior.emergency_stop(); motor.emergency_stop();
  std::cout << "emergency=" << m10::to_string(behavior.update(std::nullopt,true,true,true,true)) << '\n';
  return 0;
}
