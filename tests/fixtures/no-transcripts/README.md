This directory is intentionally empty.

Layer 2 is optional, and CI has to prove it: the end-to-end runs point --projects here so
the reading is exercised with no transcripts at all. Without a committed empty directory the
runner would fall back to the real ~/.claude/projects, which does not exist on CI either --
but then the test would be passing by accident rather than on purpose.
