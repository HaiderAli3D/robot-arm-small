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
  boot.core.tick(20); CHECK(boot.near(0,180)); CHECK(boot.near(1,0)); CHECK(boot.near(2,120)); CHECK(boot.near(3,60));
  unsigned count = boot.writes; boot.core.tick(21); CHECK(boot.writes == count);
  boot.command("hold",21); CHECK(boot.replies.back() == "OK hold 180 0 120 60");
  boot.core.tick(300); CHECK(boot.near(0,180));
  boot.command("resume",300); boot.core.tick(320); CHECK(boot.near(0,180));
  boot.command("pose 180 180 180 180",320); boot.core.tick(340); CHECK(boot.near(0,180));
  boot.command("hello",340); CHECK(boot.replies.back() == "ROBOT_ARM 1 180 180 180 180");
  boot.core.tick(400); CHECK(boot.near(0,180));

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

  Harness idle; idle.command("resume"); idle.command("pose 180 180 180 180");
  idle.core.tick(20); CHECK(idle.near(0,180));
  auto replies = idle.replies.size();
  for (uint32_t t : {500u, 1000u, 60000u, 86400000u}) {
    idle.core.tick(t); CHECK(idle.replies.size()==replies); CHECK(idle.near(0,180));
  }
  idle.command("pose 0 0 0 0",86400000); CHECK(idle.replies.back()=="OK pose");
  idle.core.tick(86400020); CHECK(idle.near(0,0));
  idle.command("pose 180 180 180 180",86400021);
  idle.command("hold",86400022); CHECK(idle.replies.back()=="OK hold 0 0 0 0");
  idle.core.tick(86400040); CHECK(idle.near(0,0));
  idle.command("pose 180 180 180 180",86400041); CHECK(idle.replies.back()=="ERR paused");
  Harness noPose; noPose.command("resume",0); noPose.core.tick(86400000);
  CHECK(noPose.replies.back()=="OK resume");
  noPose.command("pose 180 180 180 180",86400001); CHECK(noPose.replies.back()=="OK pose");
  Harness invalid; invalid.command("resume"); invalid.command("pose 180 180 180 180");
  invalid.command("pose 0 0 0 181",499); invalid.core.tick(60000);
  CHECK(invalid.replies.back()=="ERR angle"); CHECK(invalid.near(0,180));
  invalid.command("pose 0 0 0 0",60001); CHECK(invalid.replies.back()=="OK pose");

  Harness manual; manual.command("all 180"); manual.core.tick(20); CHECK(manual.near(0,180));
  manual.core.tick(1000); CHECK(manual.near(0,180)); CHECK(manual.replies.back()=="OK manual");
  manual.command("2 off",1000); CHECK(!manual.enabled[1]); CHECK(manual.enabled[0]);
  manual.core.tick(1020); CHECK(manual.near(0,180));
  manual.command("1 100",1020); manual.core.tick(1040); CHECK(manual.near(0,100)); CHECK(!manual.enabled[1]);
  manual.command("off",1040); for(unsigned i=0;i<4;++i) CHECK(!manual.enabled[i]);
  manual.command("resume",1040); for(unsigned i=0;i<4;++i) CHECK(!manual.enabled[i]);
  manual.command("pose 90 90 90 90",1040); manual.core.tick(1060); for(unsigned i=0;i<4;++i) CHECK(manual.enabled[i]);
  manual.command("help",1060); manual.command("pose 90 90 90 90",1060); CHECK(manual.replies.back()=="OK pose");

  const uint32_t start = UINT32_MAX - 100;
  Harness wrap(start); wrap.command("resume",start); wrap.command("pose 180 180 180 180",start);
  wrap.core.tick(start+20); CHECK(wrap.near(0,180));
  wrap.core.tick(start+499); CHECK(wrap.near(0,180));
  wrap.core.tick(start+500); CHECK(wrap.replies.back()=="OK pose");
  wrap.command("pose 0 0 0 0",start+600); CHECK(wrap.replies.back()=="OK pose");
  wrap.core.tick(start+620); CHECK(wrap.near(0,0));
  Harness late; late.command("resume"); late.command("pose 0 0 0 0",86400000);
  CHECK(late.replies.size()==3); CHECK(late.replies.back()=="OK pose");
  late.core.tick(86400000); CHECK(late.near(0,0));
  Harness partial; partial.command("resume"); partial.send("pose 0 0",20);
  partial.core.tick(86400000); CHECK(partial.replies.back()=="OK resume");
  partial.send(" 0 0\n",86400001); CHECK(partial.replies.back()=="OK pose");
  partial.core.tick(86400020); CHECK(partial.near(0,0));
  Harness preserved; preserved.command("resume"); preserved.command("pose 100 100 100 100");
  preserved.command("pose 0 0 0 181",1); preserved.core.tick(20);
  for (unsigned i=0;i<4;++i) CHECK(preserved.near(i,100));
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
