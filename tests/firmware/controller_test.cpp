#include "../../ESP32C5_Tracking/Controller.h"
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

#define CHECK(x) do { if (!(x)) { std::cerr << __LINE__ << ": " #x "\n"; std::exit(1); } } while (0)
struct Harness {
  std::vector<std::string> replies;
  float outputs[4] = {};
  bool enabled[4] = {};
  unsigned writes = 0;
  robot_arm::Controller core;
  Harness(uint32_t now = 0) : core(reply, output, this) { core.begin(now); }
  static void reply(void* p, const char* s) { static_cast<Harness*>(p)->replies.emplace_back(s); }
  static void output(void* p, unsigned i, float angle, bool enable) {
    auto* h = static_cast<Harness*>(p); h->outputs[i] = angle; h->enabled[i] = enable; ++h->writes;
  }
  void send(const std::string& s, uint32_t now = 0) { for (char c : s) core.receive(c, now); }
  void command(const std::string& s, uint32_t now = 0) { send(s + "\n", now); }
  bool near(unsigned i, float value) { return std::fabs(outputs[i] - value) < 0.001f; }
};

int main() {
  Harness boot;
  CHECK(boot.replies.back() == "ROBOT_ARM 1 90 90 90 90");
  for (unsigned i=0; i<4; ++i) { CHECK(boot.near(i,90)); CHECK(boot.enabled[i]); }
  boot.command("pose 0 0 0 0"); CHECK(boot.replies.back() == "ERR paused");
  boot.command("resume"); CHECK(boot.replies.back() == "OK resume");
  boot.send("pose 180 0 120 60"); CHECK(boot.replies.back() == "OK resume");
  boot.send("\r\n"); CHECK(boot.replies.back() == "OK pose");
  boot.core.tick(19); CHECK(boot.near(0,90));
  boot.core.tick(20); CHECK(boot.near(0,91.8f)); CHECK(boot.near(1,88.2f));
  unsigned count = boot.writes; boot.core.tick(21); CHECK(boot.writes == count);
  boot.command("hold",21); CHECK(boot.replies.back() == "OK hold 92 88 92 88");
  boot.core.tick(300); CHECK(boot.near(0,91.8f));
  boot.command("resume",300); boot.core.tick(320); CHECK(boot.near(0,91.8f));
  boot.command("pose 180 180 180 180",320); boot.core.tick(340); CHECK(boot.near(0,93.6f));
  boot.command("hello",340); CHECK(boot.replies.back() == "ROBOT_ARM 1 94 90 94 90");
  boot.core.tick(400); CHECK(boot.near(0,93.6f));

  const char* bad[] = {"pose 0 0 0 181", "pose 0 0 0 -1", "pose 1x 0 0 0", "pose +1 0 0 0", "pose 0 0 0 1.0", "pose 0 0 0 1e2", "pose 0 0 0 999999999999999999999999999", "pose 0 0 0", "pose 0 0 0 0 extra", "resume extra", "hold extra", "hello extra", "all 90 extra", "1 90x", "all -1", "5 90", "POSE 0 0 0 0"};
  for (const auto* cmd : bad) {
    Harness h; h.command("resume"); h.command(cmd);
    CHECK(h.replies.back().find("ERR ") == 0);
    h.core.tick(20); for(unsigned i=0;i<4;++i) CHECK(h.near(i,90));
  }
  Harness overflow; overflow.command("resume");
  overflow.command(std::string(96,'x')); CHECK(overflow.replies.back()=="ERR line_too_long");
  overflow.command("pose 100 100 100 100"); CHECK(overflow.replies.back()=="OK pose");
  overflow.command("pose 90 90 90 90" + std::string(79,' ')); CHECK(overflow.replies.back()=="OK pose");
  overflow.send(std::string("pose 0 0 0 0\0ignored\n",21)); CHECK(overflow.replies.back()=="ERR invalid_character");
  overflow.command("hold"); CHECK(overflow.replies.back()=="OK hold 90 90 90 90");

  Harness timeout; timeout.command("resume"); timeout.command("pose 180 180 180 180");
  timeout.core.tick(20); timeout.core.tick(499); CHECK(timeout.near(0,93.6f)); // No catch-up jumps.
  timeout.core.tick(500); CHECK(timeout.replies.back()=="ERR timeout"); CHECK(timeout.near(0,93.6f));
  auto replies = timeout.replies.size(); timeout.core.tick(1000); CHECK(timeout.replies.size()==replies);
  timeout.command("pose 0 0 0 0",1000); CHECK(timeout.replies.back()=="ERR paused");
  timeout.command("resume",1000); timeout.core.tick(1020); CHECK(timeout.near(0,93.6f));
  timeout.command("pose 0 0 0 0",1020); timeout.core.tick(1040); CHECK(timeout.near(0,91.8f));
  Harness noPose; noPose.command("resume",0); noPose.core.tick(500); CHECK(noPose.replies.back()=="ERR timeout");
  Harness invalidRefresh; invalidRefresh.command("resume"); invalidRefresh.command("pose 180 180 180 180");
  invalidRefresh.command("pose 0 0 0 181",499); invalidRefresh.core.tick(500); CHECK(invalidRefresh.replies.back()=="ERR timeout");

  Harness manual; manual.command("all 180"); manual.core.tick(20); CHECK(manual.near(0,91.8f));
  manual.core.tick(1000); CHECK(manual.near(0,93.6f)); CHECK(manual.replies.back()=="OK manual");
  manual.command("2 off",1000); CHECK(!manual.enabled[1]); CHECK(manual.enabled[0]);
  manual.core.tick(1020); CHECK(manual.near(0,93.6f));
  manual.command("1 100",1020); manual.core.tick(1040); CHECK(manual.near(0,95.4f)); CHECK(!manual.enabled[1]);
  manual.command("off",1040); for(unsigned i=0;i<4;++i) CHECK(!manual.enabled[i]);
  manual.command("resume",1040); for(unsigned i=0;i<4;++i) CHECK(!manual.enabled[i]);
  manual.command("pose 90 90 90 90",1040); manual.core.tick(1060); for(unsigned i=0;i<4;++i) CHECK(manual.enabled[i]);
  manual.command("help",1060); manual.command("pose 90 90 90 90",1060); CHECK(manual.replies.back()=="ERR paused");

  const uint32_t start = UINT32_MAX - 100;
  Harness wrap(start); wrap.command("resume",start); wrap.command("pose 180 180 180 180",start);
  wrap.core.tick(start+20); CHECK(wrap.near(0,91.8f));
  wrap.core.tick(start+499); CHECK(wrap.near(0,93.6f));
  wrap.core.tick(start+500); CHECK(wrap.replies.back()=="ERR timeout");
  Harness late; late.command("resume"); late.command("pose 0 0 0 0",500);
  CHECK(late.replies[late.replies.size()-2]=="ERR timeout"); CHECK(late.replies.back()=="ERR paused");
  Harness partial; partial.command("resume"); partial.send("pose 0 0",20);
  partial.core.tick(500); CHECK(partial.replies.back()=="ERR timeout");
  partial.send(" 0 0\n",501); CHECK(partial.replies.back()=="ERR paused");
  Harness preserved; preserved.command("resume"); preserved.command("pose 100 100 100 100");
  preserved.command("pose 0 0 0 181",1); preserved.core.tick(20);
  for (unsigned i=0;i<4;++i) CHECK(preserved.near(i,91.8f));
  Harness boundaries; boundaries.command("all 0");
  for (uint32_t t=20;t<=1200;t+=20) boundaries.core.tick(t);
  for(unsigned i=0;i<4;++i) CHECK(boundaries.near(i,0));
  boundaries.command("all 180",1200);
  for (uint32_t t=1220;t<=3400;t+=20) boundaries.core.tick(t);
  for(unsigned i=0;i<4;++i) CHECK(boundaries.near(i,180));
  Harness cr; cr.command("resume"); cr.send("pose 0 0\r 0 0\n");
  CHECK(cr.replies.back()=="ERR invalid_character"); cr.core.tick(20); CHECK(cr.near(0,90));
  std::cout << "Firmware production controller tests passed\n";
}
