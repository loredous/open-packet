# Talk Abstract Design: Ham Radio Village, Defcon 34

**Date:** 2026-03-24
**Status:** Draft
**Topic:** "Who Owns Your Shack?" — open source advocacy talk featuring open-packet

---

## Overview

A 30–40 minute talk for Ham Radio Village at Defcon 34. Primary audience is licensed amateur radio operators, with a secondary audience of hackers and security-minded attendees unfamiliar with the hobby. The talk uses the post-mortem license failure pattern in amateur radio software as motivating context, builds an ownership/self-reliance argument, and presents open-packet as a working existence proof of the open-source alternative.

---

## Talk Structure

### Section 1: Hook (5 min)
Open with the concrete pattern: a solo developer dies, and the software their community depended on dies with them. UI-View32 is the clean example: Roger Barker G4IDE passed in 2004, the registration servers eventually went dark, and a widely-used closed binary became unfixable. Bob Bruninga WB4APR's death in 2022 raised the same question for his reference APRS implementations and aprs.org — not the whole APRS ecosystem, but the pieces that only he maintained. Land the framing question: *you own your radio, you rely on open protocols — but do you own your software?*

### Section 2: Who Owns Your Shack? (8–10 min)
Walk the stack from hardware (owned) → protocols (open) → software (often a closed, single-developer binary). Frame the gap as a self-reliance problem — the same ethos that drives hams to build antennas and maintain gear. For the Defcon crowd: a systems resilience argument against critical infrastructure running on a black box.

### Section 3: open-packet as an Existence Proof (8–10 min)
Introduce open-packet: MIT-licensed, Python, installable from source, no license key or registration server. Briefly note that established tools like Outpost PMM carry the same succession risk — not as an attack, only as context. Quick architecture callout for the technical audience: layered design (AX.25 → KISS → engine → TUI) with swappable transport and UI. Close: *let me show you what this looks like running.*

### Section 4: Demo + Call to Action (8–10 min)
Live terminal demo: connect to a BBS node, sync messages, compose a reply (~5 min). Fallback screenshot deck for hardware failures. Remaining time: three asks + closing callback, with audience Q&A if time permits.

Three asks in order of commitment:
1. **Use it** — open-packet is installable today.
2. **Contribute** — code, bug reports, docs, TNC compatibility testing all count.
3. **Apply the lens** — ask of every tool your club depends on: what happens to this when the author is gone? Prefer open-licensed software where it exists.

Closing callback to the hook: *the software your club depends on should outlive any one of us. That's not a radical idea — it's just good engineering.*

---

## Submission Abstract

**Title:** Who Owns Your Shack? Open Source, Amateur Radio, and the Software We Can't Afford to Lose

**Abstract:**

You own your radio. The protocols you use — AX.25 and APRS — are open standards anyone can implement. But the software your club depends on? That's often a different story.

For the security-minded: this is a story about critical communication infrastructure running on software whose source code doesn't exist.

Amateur radio has a long tradition of self-reliance: building your own antennas, maintaining your own gear, understanding your own stack. That tradition breaks down at the software layer. Too much of the tooling that holds the hobby together is maintained by a single developer, distributed as a closed binary, with no source code and no succession plan. We've already seen what happens when that developer is gone: When Roger Barker G4IDE passed in 2004, UI-View32's source code went with him — leaving the community to maintain unofficial workarounds rather than fix the underlying binary, with the registration servers eventually going dark. Bob Bruninga WB4APR's death in 2022 raised the same question for his reference APRS implementations and the aprs.org site he maintained. These aren't edge cases — they're a pattern, and the hobby's aging demographics make it one we can't ignore.

This talk makes the case that open-source licensing isn't just a software philosophy — it's an infrastructure resilience strategy. If a tool is critical to your club's operations or your emergency net, its source code needs to outlive its author.

As a working example, we'll look at open-packet: an early-stage, MIT-licensed packet messaging client in Python — a working existence proof that the open-source path is viable. A brief live demo will show it connecting to a BBS node, syncing messages, and composing a reply.

Attendees will leave with a concrete lens for evaluating the software they depend on, a GitHub link, and three specific asks — from "try it" to "apply this thinking to every tool in your shack."

**Length:** 30–40 minutes
**Target venue:** Ham Radio Village, Defcon 34
**Speaker background:** Jeremy Banker (K0JLB) has been a licensed amateur radio operator since 2010, drawn to the hobby by a lifelong interest in experimentation. A Senior Security Software Engineer by trade, he is a regular packet radio operator and supports packet operations for his local ARES group. His frustration with the closed-source tools available for packet messaging — software he couldn't fix or improve — led him to build open-packet, an MIT-licensed Python client designed to outlive any single developer. He has spoken at Black Hat Arsenal, DEF CON Demo Labs, Ham Radio Village, and RMISC.

---

## Design Notes

- Outpost PMM is named only as status-quo context, not criticized directly.
- APRS and UI-View32 are used as motivating examples, not the central argument.
- The talk is structured to land for both audiences: hams hear self-reliance, hackers hear systems resilience.
- Demo is scoped to ~5 minutes with a fallback deck; open-packet is v0.1 so the demo should be simple and rehearsed.
- Speaker prep: UI-View32 did not fully stop working in 2004 — the community maintained unofficial patches and a workaround registration server. The argument is about *unfixability and dependency on a closed binary*, not total failure. Be ready to address this if challenged.
- Speaker prep: The APRS claim is scoped to Bruninga's specific tools and aprs.org, not the broader APRS ecosystem (Dire Wolf, APRS-IS, APRSdroid all remained maintained). Do not imply the whole ecosystem froze.
