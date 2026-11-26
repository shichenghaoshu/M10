#include <cassert>
#include <cstring>

#include "../esp32/m10_motor_controller/m10_protocol_core.h"

static void testCrcReferenceVector() {
  const uint8_t reference[] = {'1', '2', '3', '4', '5', '6', '7', '8', '9'};
  assert(m10::crc16CcittFalse(reference, sizeof(reference)) == 0x29B1);
}

static void testSplitNoiseAndStickyFrames() {
  uint8_t helloPayload[] = {2, 1};
  uint8_t first[m10::kMaxFrameSize];
  uint8_t second[m10::kMaxFrameSize];
  size_t firstLength = m10::encodeFrame(m10::HELLO, 0x1234, helloPayload,
                                         sizeof(helloPayload), first, sizeof(first));
  size_t secondLength = m10::encodeFrame(m10::STOP, 0x1235, NULL, 0,
                                          second, sizeof(second));
  assert(firstLength == 12);
  assert(secondLength == 10);

  m10::StreamDecoder decoder;
  m10::Frame frame;
  const uint8_t noise[] = {0x00, 0x7F, 0xAA, 0x10};
  for (size_t i = 0; i < sizeof(noise); ++i) assert(!decoder.append(noise[i], &frame));
  for (size_t i = 0; i < firstLength - 1; ++i) assert(!decoder.append(first[i], &frame));
  assert(decoder.append(first[firstLength - 1], &frame));
  assert(frame.type == m10::HELLO);
  assert(frame.sequence == 0x1234);
  assert(frame.payloadLength == 2);
  assert(std::memcmp(frame.payload, helloPayload, 2) == 0);

  bool decodedSecond = false;
  for (size_t i = 0; i < secondLength; ++i) {
    decodedSecond = decoder.append(second[i], &frame) || decodedSecond;
  }
  assert(decodedSecond);
  assert(frame.type == m10::STOP);
  assert(frame.sequence == 0x1235);
}

static void testRejectsBadCrcAndLength() {
  uint8_t encoded[m10::kMaxFrameSize];
  size_t length = m10::encodeFrame(m10::HEARTBEAT, 7, NULL, 0,
                                    encoded, sizeof(encoded));
  encoded[length - 1] ^= 0x01;
  m10::StreamDecoder decoder;
  m10::Frame frame;
  for (size_t i = 0; i < length; ++i) assert(!decoder.append(encoded[i], &frame));
  assert(decoder.crcErrors() == 1);

  const uint8_t invalidLength[] = {0xAA, 0x55, 0x02, 0x10, 0, 0, 0x01, 0x01};
  for (size_t i = 0; i < sizeof(invalidLength); ++i) {
    assert(!decoder.append(invalidLength[i], &frame));
  }
  assert(decoder.invalidLengths() == 1);
}

int main() {
  testCrcReferenceVector();
  testSplitNoiseAndStickyFrames();
  testRejectsBadCrcAndLength();
  return 0;
}
