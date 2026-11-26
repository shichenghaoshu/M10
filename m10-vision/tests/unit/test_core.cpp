#include "m10_core.hpp"
#include <cmath>
#include <cstdlib>
#include <iostream>

static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::cerr << "FAIL " << __LINE__ << ": " #x "\n"; ++failures; } } while(0)
int main() {
  auto lb=m10::make_letterbox(1280,720,640,640); auto r=m10::restore_box({0,140,640,500},lb);
  CHECK(std::abs(r.x2-1280)<0.01F && std::abs(r.y2-720)<0.01F);
  CHECK(std::abs(m10::dequantize_int8(10,2,0.25F)-2.0F)<0.001F);
  auto kept=m10::nms({{15,"cat",.9F,{0,0,100,100}},{15,"cat",.8F,{5,5,95,95}},{16,"dog",.7F,{5,5,95,95}}},.45F); CHECK(kept.size()==2);
  m10::SimpleTracker tracker(.2F,2); auto t1=tracker.update({{15,"cat",.9F,{10,10,100,100}}},640,480); auto t2=tracker.update({{15,"cat",.9F,{15,10,105,100}}},640,480); CHECK(t1[0].track_id==t2[0].track_id);
  m10::MockMotorDriver motor; CHECK(motor.initialize()); CHECK(motor.stop()); motor.set_healthy(false); CHECK(!motor.send({2,m10::Motion::FORWARD,20,20,100}));
  auto wire=m10::encode_motor_command({7,m10::Motion::STOP,0,0,0}); CHECK(wire.rfind("M10,7,STOP,0,0,0,",0)==0);
  auto safe_wire=m10::encode_motor_command({8,m10::Motion::EMERGENCY_STOP,90,90,9999}); CHECK(safe_wire.rfind("M10,8,EMERGENCY_STOP,0,0,0,",0)==0);
  m10::SerialEsp32MotorDriver absent("/definitely/not/a/serial/device"); CHECK(!absent.initialize()); CHECK(!absent.healthy());
  m10::BehaviorMachine state; state.request(m10::State::FOLLOW_PET); CHECK(state.update(t2[0],true,true,true,false)==m10::Motion::STOP); CHECK(state.state()==m10::State::OBSTACLE_STOP);
  state.emergency_stop(); CHECK(state.update(std::nullopt,true,true,true,true)==m10::Motion::EMERGENCY_STOP);
  m10::GestureDebouncer gestures(800,2000,.45F); std::map<std::string,m10::Keypoint> pose{{"left_wrist",{0,0,.9F}},{"right_wrist",{1,0,.9F}},{"left_shoulder",{0,1,.9F}},{"right_shoulder",{1,1,.9F}}};
  CHECK(gestures.update(pose,true,0)==m10::Gesture::NONE); CHECK(gestures.update(pose,true,799)==m10::Gesture::NONE); CHECK(gestures.update(pose,true,800)==m10::Gesture::STOP);
  CHECK(m10::identity_match({1,0,0},{.9F,.1F,0},.9F)); CHECK(!m10::identity_match({1,0},{0,1},.5F));
  CHECK(!m10::conservative_traversability(.9F,false,true).safe_to_move); CHECK(m10::conservative_traversability(.8F,false,false).safe_to_move);
  m10::SearchController search(2,30000,300,200);search.start(0,true);CHECK(search.update(0,false,true,true)==m10::Motion::ROTATE_LEFT);CHECK(search.update(100,false,true,true)==m10::Motion::STOP);CHECK(search.update(500,false,true,true)==m10::Motion::ROTATE_RIGHT);CHECK(search.update(1000,false,true,true)==m10::Motion::STOP&&!search.active());
  if(failures) return EXIT_FAILURE; std::cout << "PASS m10_core_tests\n"; return EXIT_SUCCESS;
}
