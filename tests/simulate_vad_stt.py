# simulate_vad_stt.py
import time
from livekit_agents.utils.interrupt_handler import InterruptHandler, InterruptHandlerConfig, Transcript

# Simple logger
def logger(msg): print(msg)

# Agent speaking state variable
_agent_speaking = False
def get_agent_speaking_state():
    return _agent_speaking

def stop_agent_immediately():
    global _agent_speaking
    logger(f"[{time.strftime('%H:%M:%S')}] ACTION: stop_agent_immediately() called -> stopping playback.")
    _agent_speaking = False

def ignore_user_speech():
    logger(f"[{time.strftime('%H:%M:%S')}] ACTION: ignore_user_speech() called -> continuing playback.")

def process_user_speech_normally(t: Transcript):
    logger(f"[{time.strftime('%H:%M:%S')}] ACTION: process_user_speech_normally() -> user said: '{t.text}'")

cfg = InterruptHandlerConfig(validation_window_ms=225)
ih = InterruptHandler(cfg, stop_agent_immediately, ignore_user_speech, process_user_speech_normally, get_agent_speaking_state, logger=logger)

def simulate_scenario_1_long_explanation():
    global _agent_speaking
    logger("=== Scenario 1: Agent speaking; user backchannels 'Okay... yeah... uh-huh' ===")
    _agent_speaking = True
    ih.agent_started_speaking()
    # VAD fires immediately when user says something
    ih.on_vad_user_started()
    # STT partials come shortly after (simulate)
    time.sleep(0.12)  # 120ms
    ih.on_stt_transcript(Transcript("okay", is_final=False))
    time.sleep(0.06)  # 60ms
    ih.on_stt_transcript(Transcript("yeah", is_final=False))
    time.sleep(0.04)
    ih.on_stt_transcript(Transcript("uh-huh", is_final=True))
    # sleep to allow any timers to finish
    time.sleep(0.3) 

def simulate_scenario_2_passive_affirmation():
    global _agent_speaking
    logger("=== Scenario 2: Agent silent; user says 'Yeah' ===")
    _agent_speaking = False
    ih.agent_stopped_speaking()
    ih.on_vad_user_started()
    time.sleep(0.08)
    ih.on_stt_transcript(Transcript("yeah", is_final=True))
    time.sleep(0.15)

def simulate_scenario_3_correction():
    global _agent_speaking
    logger("=== Scenario 3: Agent speaking; user says 'No stop' ===")
    _agent_speaking = True
    ih.agent_started_speaking()
    ih.on_vad_user_started()
    time.sleep(0.07)
    ih.on_stt_transcript(Transcript("no stop", is_final=True))
    time.sleep(0.15)

def simulate_scenario_4_mixed_input():
    global _agent_speaking
    logger("=== Scenario 4: Agent speaking; user says 'Yeah okay but wait' ===")
    _agent_speaking = True
    ih.agent_started_speaking()
    ih.on_vad_user_started()
    time.sleep(0.09)
    ih.on_stt_transcript(Transcript("yeah okay but wait", is_final=True))
    time.sleep(0.2)

if __name__ == "__main__":
    simulate_scenario_1_long_explanation()
    simulate_scenario_2_passive_affirmation()
    simulate_scenario_3_correction()
    simulate_scenario_4_mixed_input()
    logger("=== Simulation complete ===")
