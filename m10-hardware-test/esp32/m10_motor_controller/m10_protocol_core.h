#ifndef M10_PROTOCOL_CORE_H
#define M10_PROTOCOL_CORE_H

#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace m10 {

static const uint8_t kHeader0 = 0xAA;
static const uint8_t kHeader1 = 0x55;
static const uint8_t kVersion = 2;
static const size_t kMaxPayload = 256;
static const size_t kMaxFrameSize = 10 + kMaxPayload;

enum MessageType : uint8_t {
  HELLO = 0x01,
  HELLO_ACK = 0x02,
  HEARTBEAT = 0x03,
  ACK = 0x04,
  SET_MOTOR = 0x10,
  STOP = 0x11,
  EMERGENCY_STOP = 0x12,
  CLEAR_EMERGENCY_STOP = 0x13,
  SET_CONTROL_MODE = 0x14,
  TELEMETRY = 0x20,
  SENSOR_STATE = 0x21,
  FAULT = 0x22,
  CONNECTION_STATS = 0x23,
  GET_CONFIG = 0x30,
  CONFIG = 0x31,
  SET_CONFIG = 0x32,
  SAVE_CONFIG = 0x33,
  PING = 0x40,
  PONG = 0x41,
};

struct Frame {
  uint8_t version;
  uint8_t type;
  uint16_t sequence;
  uint16_t payloadLength;
  uint8_t payload[kMaxPayload];
};

inline uint16_t getLe16(const uint8_t *data) {
  return static_cast<uint16_t>(data[0]) |
         static_cast<uint16_t>(static_cast<uint16_t>(data[1]) << 8);
}

inline int16_t getSignedLe16(const uint8_t *data) {
  return static_cast<int16_t>(getLe16(data));
}

inline void putLe16(uint8_t *data, uint16_t value) {
  data[0] = static_cast<uint8_t>(value & 0xFF);
  data[1] = static_cast<uint8_t>((value >> 8) & 0xFF);
}

inline uint16_t crc16CcittFalse(const uint8_t *data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < length; ++i) {
    crc ^= static_cast<uint16_t>(data[i]) << 8;
    for (uint8_t bit = 0; bit < 8; ++bit) {
      crc = (crc & 0x8000) ? static_cast<uint16_t>((crc << 1) ^ 0x1021)
                           : static_cast<uint16_t>(crc << 1);
    }
  }
  return crc;
}

inline size_t encodeFrame(uint8_t type, uint16_t sequence, const uint8_t *payload,
                          uint16_t payloadLength, uint8_t *output, size_t capacity) {
  if (payloadLength > kMaxPayload || capacity < 10u + payloadLength) return 0;
  output[0] = kHeader0;
  output[1] = kHeader1;
  output[2] = kVersion;
  output[3] = type;
  putLe16(output + 4, sequence);
  putLe16(output + 6, payloadLength);
  if (payloadLength > 0 && payload != NULL) memcpy(output + 8, payload, payloadLength);
  uint16_t crc = crc16CcittFalse(output + 2, 6u + payloadLength);
  putLe16(output + 8 + payloadLength, crc);
  return 10u + payloadLength;
}

class StreamDecoder {
 public:
  StreamDecoder() : size_(0), crcErrors_(0), invalidLengths_(0), discardedBytes_(0) {}

  bool append(uint8_t byte, Frame *frame) {
    if (frame == NULL) return false;

    if (size_ == 0) {
      if (byte == kHeader0) buffer_[size_++] = byte;
      else ++discardedBytes_;
      return false;
    }
    if (size_ == 1) {
      if (byte == kHeader1) {
        buffer_[size_++] = byte;
      } else if (byte == kHeader0) {
        buffer_[0] = byte;
        ++discardedBytes_;
      } else {
        resetFrame();
        ++discardedBytes_;
      }
      return false;
    }

    if (size_ >= kMaxFrameSize) {
      resetFrame();
      ++discardedBytes_;
      return false;
    }
    buffer_[size_++] = byte;

    if (size_ == 8) {
      uint16_t payloadLength = getLe16(buffer_ + 6);
      if (payloadLength > kMaxPayload) {
        ++invalidLengths_;
        resyncFromLastByte();
      }
      return false;
    }
    if (size_ < 8) return false;

    uint16_t payloadLength = getLe16(buffer_ + 6);
    size_t expectedSize = 10u + payloadLength;
    if (size_ < expectedSize) return false;
    if (size_ > expectedSize) {
      resyncFromLastByte();
      return false;
    }

    uint16_t expectedCrc = getLe16(buffer_ + 8 + payloadLength);
    uint16_t actualCrc = crc16CcittFalse(buffer_ + 2, 6u + payloadLength);
    if (expectedCrc != actualCrc) {
      ++crcErrors_;
      resyncFromLastByte();
      return false;
    }

    frame->version = buffer_[2];
    frame->type = buffer_[3];
    frame->sequence = getLe16(buffer_ + 4);
    frame->payloadLength = payloadLength;
    if (payloadLength > 0) memcpy(frame->payload, buffer_ + 8, payloadLength);
    resetFrame();
    return true;
  }

  uint32_t crcErrors() const { return crcErrors_; }
  uint32_t invalidLengths() const { return invalidLengths_; }
  uint32_t discardedBytes() const { return discardedBytes_; }

 private:
  void resetFrame() { size_ = 0; }

  void resyncFromLastByte() {
    uint8_t last = size_ > 0 ? buffer_[size_ - 1] : 0;
    size_ = 0;
    if (last == kHeader0) buffer_[size_++] = last;
  }

  uint8_t buffer_[kMaxFrameSize];
  size_t size_;
  uint32_t crcErrors_;
  uint32_t invalidLengths_;
  uint32_t discardedBytes_;
};

}  // namespace m10

#endif
