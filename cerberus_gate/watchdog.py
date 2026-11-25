"""THE WATCHDOG (v2.8.1) - the conscience never sleeps, and now neither
does its guard.

The conscience catches a rough AI at the gate: every outbound packet is
judged before it moves, a veto is a strike on the agent that fired it,
three strikes put that agent on probation without a human, honest work
restores it. That loop is automatic. What it cannot see is a move that
SKIPS the conscience entirely - a hand editing the memory file behind
the god's back, a tampered shield ledger, a record rewritten out of
band. The watchdog exists for exactly that gap:

  - a daemon thread re-verifies the memory chain and the shield's own
    hash-chained ledger on a fixed tick (default 20s),
  - anything broken becomes an incident in the book and an alert,
  - a clean pass ends with a fresh checkpoint, so the honest copy of
    the record exists outside the mind's reach.

CERBERUS_WATCHDOG=0 turns it off (tests, containers with their own
supervisor). CERBERUS_WATCHDOG_SECONDS sets the tick. The watchdog never
blocks a verb and never touches the wire - it watches, remembers, and
names what it found. That is the whole job.
"""
import os
import threading
import traceback

from .incidents import Incident, IncidentBook


class Watchdog:
    """Every tick: re-verify the memory chain and the shield ledger.
    Broken? Record the incident, dispatch the alert, checkpoint the
    mirror. pass_once() is also usable by hand (tests, dashboards).

    v3.0.0b4 THE QUIET WATCH: the tick first takes a (size, mtime)
    stamp of the wal and the shield ledger and SKIPS the whole pass
    when neither has moved since the last clean look. b3 re-verified
    the ENTIRE record and copied the ENTIRE wal to the mirror every
    twenty seconds, forever, in the same process that serves MCP - on
    a grown mind that was continuous CPU and disk churn competing with
    every tool call (the law_status timeout chain). The guard watches
    the same files for the same breakage: anything that changes gets
    a full pass, anything that did not cannot have new breakage.
    """

    def __init__(self, mind, interval=None):
        self.mind = mind
        try:
            iv = float(interval or os.environ.get("CERBERUS_WATCHDOG_SECONDS", "20") or 20)
        except (TypeError, ValueError):
            iv = 20.0
        self.interval = max(iv, 0.05)
        self.threads = 0          # passes completed
        self.skipped = 0          # ticks where nothing changed - no pass needed
        self.found = 0            # passes that found something broken
        self.findings = []        # the last problems, newest first
        self._last_clean_stamp = None
        self._stop = threading.Event()
        self._t = None

    def _stamp(self):
        """One cheap number-pair per watched file - no content read."""
        stamps = []
        for f in (self.mind.wal,
                  self.mind.base / "realm" / "shield-ledger.jsonl"):
            try:
                st = f.stat()
                stamps.append((str(f), st.st_size, st.st_mtime_ns))
            except OSError:
                stamps.append((str(f), -1, -1))
        return tuple(stamps)

    def start(self):
        if self._t is not None:
            return self
        self._t = threading.Thread(target=self._loop, daemon=True,
                                   name="Cerberus-watchdog")
        self._t.start()
        return self

    def stop(self):
        self._stop.set()
        if self._t is not None:
            self._t.join(timeout=2)
            self._t = None
        return self

    def _loop(self):
        while not self._stop.wait(self.interval):
            try:
                self.pass_once()
            except Exception:
                # the watchdog must never die loudly - a failed tick is
                # itself a finding, recorded where the owner reads
                self.found += 1
                self.findings.insert(0, "watchdog tick failed: %s"
                                     % traceback.format_exc()[-200:])
                del self.findings[50:]

    def pass_once(self, force=False):
        """One verification pass. Returns the problems it found (empty
        list = the record and the ledger stand). An unchanged record
        since the last CLEAN pass is skipped (v3.0.0b4) - pass None is
        not "not checked", it is "nothing moved"; force=True runs the
        full pass anyway (owner audits, tests)."""
        self.threads += 1
        stamp = self._stamp()
        if (not force and self._last_clean_stamp is not None
                and stamp == self._last_clean_stamp):
            self.skipped += 1
            return []
        problems = []
        try:
            mv = self.mind.verify()
            if not mv.get("ok"):
                problems.append("memory chain: %s (%s)"
                                % (mv.get("verdict"), mv.get("detail")))
        except Exception as e:
            problems.append("memory verify failed: %s" % e.__class__.__name__)
        try:
            from . import blast_shield
            led = blast_shield.get_ledger(self.mind.base)
            if led is not None:
                lv = led.verify()
                if not lv.get("intact"):
                    problems.append("shield ledger: %s"
                                    % (lv.get("detail") or lv.get("reason") or "broken"))
        except Exception as e:
            problems.append("shield consult failed: %s" % e.__class__.__name__)
        if problems:
            self.found += 1
            for p in problems:
                self.findings.insert(0, p)
            del self.findings[50:]
            self._record(problems)
        else:
            # the record is clean AT THIS STAMP - remember it, so the
            # next tick can skip instead of re-verifying the same bytes
            self._last_clean_stamp = stamp
            try:
                self.mind.checkpoint()
            except Exception:
                pass
        return problems

    def _record(self, problems):
        try:
            book = IncidentBook(self.mind.base)
            for p in problems:
                book.record(Incident(
                    "watchdog_alert", "watchdog", str(self.mind.mind),
                    "a rough move that skipped the conscience: %s" % p,
                    "background verification tick", "watchdog found it",
                    "incident recorded, alert dispatched, mirror checkpointed",
                    agent="watchdog"))
            from .enterprise import dispatch_alert
            dispatch_alert(self.mind.base,
                           {"kind": "watchdog", "problems": problems})
        except Exception:
            pass
