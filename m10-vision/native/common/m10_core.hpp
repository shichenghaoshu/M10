#pragma once

#include <cstdint>
#include <deque>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace m10 {

struct Rect { float x1{}, y1{}, x2{}, y2{}; float area() const; };
struct Detection { int class_id{}; std::string class_name; float confidence{}; Rect bbox; };
struct TrackedObject {
  int track_id{}, class_id{}, age{}, lost_frames{};
  float confidence{}, normalized_area{};
  Rect bbox;
  float center_x{}, center_y{}, velocity_x{}, velocity_y{};
};
struct Letterbox { float scale{}; float pad_x{}, pad_y{}; int input_w{}, input_h{}, source_w{}, source_h{}; };

Letterbox make_letterbox(int source_w, int source_h, int input_w, int input_h);
Rect restore_box(const Rect& model_box, const Letterbox& transform);
float iou(const Rect& a, const Rect& b);
float dequantize_int8(int8_t value, int32_t zero_point, float scale);
std::vector<Detection> nms(std::vector<Detection> detections, float threshold);

class SimpleTracker {
 public:
  SimpleTracker(float match_iou = 0.3F, int max_lost = 30);
  std::vector<TrackedObject> update(const std::vector<Detection>& detections, int frame_w, int frame_h);
 private:
  int next_id_{1}; float match_iou_; int max_lost_; std::vector<TrackedObject> tracks_;
};

enum class State { IDLE, SEARCH_PET, TRACK_PET, FOLLOW_PET, SEARCH_OWNER, TRACK_OWNER,
  FOLLOW_OWNER, GESTURE_CONTROL, OBSTACLE_STOP, TARGET_LOST, EMERGENCY_STOP, ERROR };
enum class Motion { STOP, FORWARD, BACKWARD, TURN_LEFT, TURN_RIGHT, ROTATE_LEFT,
  ROTATE_RIGHT, SLOW_FORWARD, EMERGENCY_STOP };
std::string to_string(State value);
std::string to_string(Motion value);

struct ControlConfig {
  float center_dead_zone{0.12F}, target_area_min{0.05F}, target_area_max{0.25F};
  float confidence_threshold{0.45F}; int target_lost_frames{15};
};

class BehaviorMachine {
 public:
  explicit BehaviorMachine(ControlConfig config = {});
  void request(State state);
  Motion update(const std::optional<TrackedObject>& target, bool camera_ok, bool inference_ok,
                bool motor_ok, bool path_safe);
  void emergency_stop();
  State state() const { return state_; }
 private:
  ControlConfig config_; State state_{State::IDLE}; int lost_{0};
};

class SearchController {
 public:
  SearchController(int max_steps=12, int total_timeout_ms=30000, int step_ms=300, int settle_ms=200);
  void start(int64_t now_ms, bool last_seen_left);
  Motion update(int64_t now_ms, bool target_found, bool path_safe, bool systems_ok);
  bool active() const { return active_; } int steps() const { return steps_; }
 private:
  int max_steps_, timeout_ms_, step_ms_, settle_ms_, steps_{0}; int64_t started_{0}, next_step_{0}; bool left_{true}, active_{false};
};

struct MotorCommand { uint32_t sequence{}; Motion motion{Motion::STOP}; int left_speed{}, right_speed{}, duration_ms{}; };
uint16_t crc16_ccitt(const std::string& data);
std::string encode_motor_command(const MotorCommand& command);
class MotorDriver {
 public:
  virtual bool initialize() = 0; virtual bool send(const MotorCommand&) = 0;
  virtual bool stop() = 0; virtual bool emergency_stop() = 0; virtual bool healthy() const = 0;
  virtual ~MotorDriver() = default;
};
class MockMotorDriver final : public MotorDriver {
 public:
  bool initialize() override; bool send(const MotorCommand& command) override; bool stop() override; bool emergency_stop() override;
  bool healthy() const override { return healthy_; } const std::vector<MotorCommand>& history() const { return history_; }
  void set_healthy(bool value) { healthy_ = value; }
 private: bool healthy_{false}; std::vector<MotorCommand> history_;
};
class SerialEsp32MotorDriver final : public MotorDriver {
 public:
  explicit SerialEsp32MotorDriver(std::string device, int ack_timeout_ms = 300);
  ~SerialEsp32MotorDriver() override;
  bool initialize() override; bool send(const MotorCommand& command) override;
  bool stop() override; bool emergency_stop() override; bool healthy() const override { return healthy_; }
 private:
  bool await_ack(uint32_t sequence); std::string device_; int ack_timeout_ms_; int fd_{-1}; bool healthy_{false}; uint32_t sequence_{1};
};

struct Keypoint { float x{}, y{}, confidence{}; };
enum class Gesture { NONE, STOP, COME, FOLLOW_PET };
class GestureDebouncer {
 public:
  GestureDebouncer(int hold_ms = 800, int cooldown_ms = 2000, float threshold = 0.45F);
  Gesture update(const std::map<std::string, Keypoint>& pose, bool owner_confirmed, int64_t now_ms);
 private:
  Gesture classify(const std::map<std::string, Keypoint>& pose) const;
  int hold_ms_, cooldown_ms_; float threshold_; Gesture candidate_{Gesture::NONE};
  int64_t candidate_since_{0}, cooldown_until_{0};
};

float cosine_similarity(const std::vector<float>& a, const std::vector<float>& b);
bool identity_match(const std::vector<float>& probe, const std::vector<float>& owner, float threshold);

struct TraversabilityResult { float center_path_score{}; bool safe_to_move{}; bool heuristic_fallback{true}; };
TraversabilityResult conservative_traversability(float visible_floor_ratio, bool dynamic_obstacle,
                                                 bool unknown_center, float min_score = 0.65F);

}  // namespace m10
