#include "m10_core.hpp"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <fcntl.h>
#include <poll.h>
#include <termios.h>
#include <unistd.h>

namespace m10 {

float Rect::area() const { return std::max(0.0F, x2 - x1) * std::max(0.0F, y2 - y1); }

Letterbox make_letterbox(int sw, int sh, int iw, int ih) {
  if (sw <= 0 || sh <= 0 || iw <= 0 || ih <= 0) throw std::invalid_argument("invalid image size");
  const float scale = std::min(static_cast<float>(iw) / sw, static_cast<float>(ih) / sh);
  return {scale, (iw - sw * scale) * 0.5F, (ih - sh * scale) * 0.5F, iw, ih, sw, sh};
}

Rect restore_box(const Rect& b, const Letterbox& t) {
  auto x = [&](float value) { return std::clamp((value - t.pad_x) / t.scale, 0.0F, static_cast<float>(t.source_w)); };
  auto y = [&](float value) { return std::clamp((value - t.pad_y) / t.scale, 0.0F, static_cast<float>(t.source_h)); };
  return {x(b.x1), y(b.y1), x(b.x2), y(b.y2)};
}

float iou(const Rect& a, const Rect& b) {
  Rect overlap{std::max(a.x1,b.x1), std::max(a.y1,b.y1), std::min(a.x2,b.x2), std::min(a.y2,b.y2)};
  const float intersection = overlap.area(); const float total = a.area() + b.area() - intersection;
  return total <= 0.0F ? 0.0F : intersection / total;
}

float dequantize_int8(int8_t value, int32_t zero_point, float scale) {
  return (static_cast<int32_t>(value) - zero_point) * scale;
}

std::vector<Detection> nms(std::vector<Detection> input, float threshold) {
  std::sort(input.begin(), input.end(), [](const auto& a, const auto& b) { return a.confidence > b.confidence; });
  std::vector<Detection> output;
  for (const auto& candidate : input) {
    bool suppressed = false;
    for (const auto& kept : output) if (candidate.class_id == kept.class_id && iou(candidate.bbox, kept.bbox) > threshold) { suppressed = true; break; }
    if (!suppressed) output.push_back(candidate);
  }
  return output;
}

SimpleTracker::SimpleTracker(float match_iou, int max_lost) : match_iou_(match_iou), max_lost_(max_lost) {}

std::vector<TrackedObject> SimpleTracker::update(const std::vector<Detection>& detections, int fw, int fh) {
  std::vector<bool> used(detections.size(), false);
  for (auto& track : tracks_) {
    int best = -1; float best_iou = match_iou_;
    for (size_t i = 0; i < detections.size(); ++i) {
      if (used[i] || detections[i].class_id != track.class_id) continue;
      const float score = iou(track.bbox, detections[i].bbox); if (score > best_iou) { best_iou = score; best = static_cast<int>(i); }
    }
    if (best >= 0) {
      const auto& d = detections[best]; used[best] = true;
      const float nx = (d.bbox.x1 + d.bbox.x2) * 0.5F / fw, ny = (d.bbox.y1 + d.bbox.y2) * 0.5F / fh;
      track.velocity_x = nx - track.center_x; track.velocity_y = ny - track.center_y;
      track.center_x = nx; track.center_y = ny; track.bbox = d.bbox; track.confidence = d.confidence;
      track.normalized_area = d.bbox.area() / (fw * static_cast<float>(fh)); track.age++; track.lost_frames = 0;
    } else { track.lost_frames++; track.age++; }
  }
  tracks_.erase(std::remove_if(tracks_.begin(), tracks_.end(), [&](const auto& t){ return t.lost_frames > max_lost_; }), tracks_.end());
  for (size_t i = 0; i < detections.size(); ++i) if (!used[i]) {
    const auto& d = detections[i];
    tracks_.push_back({next_id_++, d.class_id, 1, 0, d.confidence, d.bbox.area()/(fw*static_cast<float>(fh)), d.bbox,
      (d.bbox.x1+d.bbox.x2)*0.5F/fw, (d.bbox.y1+d.bbox.y2)*0.5F/fh, 0, 0});
  }
  return tracks_;
}

std::string to_string(State s) {
  static const char* names[] = {"IDLE","SEARCH_PET","TRACK_PET","FOLLOW_PET","SEARCH_OWNER","TRACK_OWNER","FOLLOW_OWNER","GESTURE_CONTROL","OBSTACLE_STOP","TARGET_LOST","EMERGENCY_STOP","ERROR"};
  return names[static_cast<int>(s)];
}
std::string to_string(Motion m) {
  static const char* names[] = {"STOP","FORWARD","BACKWARD","TURN_LEFT","TURN_RIGHT","ROTATE_LEFT","ROTATE_RIGHT","SLOW_FORWARD","EMERGENCY_STOP"};
  return names[static_cast<int>(m)];
}

BehaviorMachine::BehaviorMachine(ControlConfig config) : config_(config) {}
void BehaviorMachine::request(State requested) { if (state_ != State::EMERGENCY_STOP) { state_ = requested; lost_ = 0; } }
void BehaviorMachine::emergency_stop() { state_ = State::EMERGENCY_STOP; }
Motion BehaviorMachine::update(const std::optional<TrackedObject>& target, bool camera_ok, bool inference_ok, bool motor_ok, bool path_safe) {
  if (state_ == State::EMERGENCY_STOP) return Motion::EMERGENCY_STOP;
  if (!camera_ok || !inference_ok || !motor_ok) { state_ = State::ERROR; return Motion::STOP; }
  if (!path_safe) { state_ = State::OBSTACLE_STOP; return Motion::STOP; }
  if (!target || target->confidence < config_.confidence_threshold) {
    if (++lost_ > config_.target_lost_frames) state_ = State::TARGET_LOST;
    return Motion::STOP;
  }
  lost_ = 0;
  if (state_ == State::SEARCH_PET || state_ == State::TARGET_LOST) state_ = State::TRACK_PET;
  if (state_ == State::SEARCH_OWNER) state_ = State::TRACK_OWNER;
  if (target->normalized_area > config_.target_area_max) return Motion::BACKWARD;
  if (target->center_x < 0.5F - config_.center_dead_zone) return Motion::TURN_LEFT;
  if (target->center_x > 0.5F + config_.center_dead_zone) return Motion::TURN_RIGHT;
  if (target->normalized_area < config_.target_area_min) return target->confidence < 0.6F ? Motion::SLOW_FORWARD : Motion::FORWARD;
  return Motion::STOP;
}

SearchController::SearchController(int max_steps,int timeout,int step,int settle):max_steps_(max_steps),timeout_ms_(timeout),step_ms_(step),settle_ms_(settle){}
void SearchController::start(int64_t now,bool last_left){started_=now;next_step_=now;steps_=0;left_=last_left;active_=true;}
Motion SearchController::update(int64_t now,bool found,bool safe,bool systems_ok){
  if(!active_)return Motion::STOP;if(found||!safe||!systems_ok||steps_>=max_steps_||now-started_>=timeout_ms_){active_=false;return Motion::STOP;}
  if(now<next_step_)return Motion::STOP;const Motion result=left_?Motion::ROTATE_LEFT:Motion::ROTATE_RIGHT;left_=!left_;steps_++;next_step_=now+step_ms_+settle_ms_;return result;
}

uint16_t crc16_ccitt(const std::string& data) {
  uint16_t crc = 0xFFFFU; for (unsigned char c : data) { crc ^= static_cast<uint16_t>(c) << 8U; for (int i=0;i<8;i++) crc = crc & 0x8000U ? (crc << 1U) ^ 0x1021U : crc << 1U; } return crc;
}
std::string encode_motor_command(const MotorCommand& c) {
  const bool stopping = c.motion == Motion::STOP || c.motion == Motion::EMERGENCY_STOP;
  const int left = stopping ? 0 : std::clamp(c.left_speed, -100, 100);
  const int right = stopping ? 0 : std::clamp(c.right_speed, -100, 100);
  const int duration = stopping ? 0 : std::clamp(c.duration_ms, 0, 500);
  std::ostringstream body; body << "M10," << c.sequence << ',' << to_string(c.motion) << ',' << left << ',' << right << ',' << duration;
  std::ostringstream out; out << body.str() << ',' << std::uppercase << std::hex << std::setw(4) << std::setfill('0') << crc16_ccitt(body.str()) << '\n'; return out.str();
}
bool MockMotorDriver::initialize() { healthy_ = true; return true; }
bool MockMotorDriver::send(const MotorCommand& c) { if (!healthy_) return false; history_.push_back(c); return true; }
bool MockMotorDriver::stop() { return send({static_cast<uint32_t>(history_.size()+1), Motion::STOP,0,0,0}); }
bool MockMotorDriver::emergency_stop() { return send({static_cast<uint32_t>(history_.size()+1), Motion::EMERGENCY_STOP,0,0,0}); }

SerialEsp32MotorDriver::SerialEsp32MotorDriver(std::string device, int timeout) : device_(std::move(device)), ack_timeout_ms_(timeout) {}
SerialEsp32MotorDriver::~SerialEsp32MotorDriver() { if (fd_ >= 0) { const auto stop_wire=encode_motor_command({sequence_++,Motion::STOP,0,0,0}); ::write(fd_,stop_wire.data(),stop_wire.size()); ::close(fd_); } }
bool SerialEsp32MotorDriver::initialize() {
  fd_=::open(device_.c_str(),O_RDWR|O_NOCTTY|O_NONBLOCK); if(fd_<0)return false; termios tty{};
  if(tcgetattr(fd_,&tty)!=0){::close(fd_);fd_=-1;return false;} cfsetispeed(&tty,B115200);cfsetospeed(&tty,B115200);
  tty.c_cflag=(tty.c_cflag&~CSIZE)|CS8;tty.c_cflag|=CLOCAL|CREAD;tty.c_cflag&=~(PARENB|CSTOPB|CRTSCTS);tty.c_lflag=0;tty.c_iflag=0;tty.c_oflag=0;
  if(tcsetattr(fd_,TCSANOW,&tty)!=0){::close(fd_);fd_=-1;return false;} healthy_=true; return stop();
}
bool SerialEsp32MotorDriver::await_ack(uint32_t sequence) {
  pollfd descriptor{fd_,POLLIN,0}; if(::poll(&descriptor,1,ack_timeout_ms_)<=0)return false; char buffer[256]{};const auto count=::read(fd_,buffer,sizeof(buffer)-1);if(count<=0)return false;
  const std::string expected="ACK,"+std::to_string(sequence)+",";return std::string(buffer,static_cast<size_t>(count)).find(expected)!=std::string::npos;
}
bool SerialEsp32MotorDriver::send(const MotorCommand& input) {
  if(!healthy_||fd_<0)return false;MotorCommand command=input;if(command.sequence==0)command.sequence=sequence_++;const auto wire=encode_motor_command(command);
  if(::write(fd_,wire.data(),wire.size())!=static_cast<ssize_t>(wire.size())||!await_ack(command.sequence)){healthy_=false;return false;}return true;
}
bool SerialEsp32MotorDriver::stop(){return send({sequence_++,Motion::STOP,0,0,0});}
bool SerialEsp32MotorDriver::emergency_stop(){return send({sequence_++,Motion::EMERGENCY_STOP,0,0,0});}

GestureDebouncer::GestureDebouncer(int hold, int cooldown, float threshold) : hold_ms_(hold), cooldown_ms_(cooldown), threshold_(threshold) {}
Gesture GestureDebouncer::classify(const std::map<std::string,Keypoint>& p) const {
  for (const auto* key : {"left_wrist","right_wrist","left_shoulder","right_shoulder"}) if (!p.count(key) || p.at(key).confidence < threshold_) return Gesture::NONE;
  const bool left = p.at("left_wrist").y < p.at("left_shoulder").y, right = p.at("right_wrist").y < p.at("right_shoulder").y;
  if (left && right) return Gesture::STOP; if (right && !left) return Gesture::COME; if (left && !right) return Gesture::FOLLOW_PET; return Gesture::NONE;
}
Gesture GestureDebouncer::update(const std::map<std::string,Keypoint>& pose, bool owner, int64_t now) {
  if (!owner || now < cooldown_until_) return Gesture::NONE; const Gesture current = classify(pose);
  if (current == Gesture::NONE) { candidate_ = current; candidate_since_ = 0; return current; }
  if (current != candidate_) { candidate_ = current; candidate_since_ = now; return Gesture::NONE; }
  if (now - candidate_since_ < hold_ms_) return Gesture::NONE; cooldown_until_ = now + cooldown_ms_; candidate_ = Gesture::NONE; return current;
}

float cosine_similarity(const std::vector<float>& a, const std::vector<float>& b) {
  if (a.size()!=b.size() || a.empty()) return -1.0F; double dot=0, aa=0, bb=0; for(size_t i=0;i<a.size();++i){dot+=a[i]*b[i];aa+=a[i]*a[i];bb+=b[i]*b[i];}
  return aa==0||bb==0 ? -1.0F : static_cast<float>(dot/std::sqrt(aa*bb));
}
bool identity_match(const std::vector<float>& a, const std::vector<float>& b, float threshold) { return cosine_similarity(a,b) >= threshold; }
TraversabilityResult conservative_traversability(float floor, bool obstacle, bool unknown, float min_score) {
  const float score = std::clamp(floor,0.0F,1.0F); return {score, !obstacle && !unknown && score >= min_score, true};
}

}  // namespace m10
