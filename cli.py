"""Chat with SnackBot in the terminal.  Run:  python cli.py   (commands: /reset, /quit)"""
import getpass
import uuid

from snackbot import config
from snackbot.agent import SnackBot
from snackbot.tracing import flush, setup_tracing


def main():
    setup_tracing()  # PHASE 1: must run before the first LLM call
    bot, history = SnackBot(), []
    session_id = str(uuid.uuid4())   # PHASE 1: one session = one conversation in Phoenix
    user_id = getpass.getuser()
    print("SnackBot ready. Ask about Crunchwell Foods. Type /reset to clear history, /quit to exit.\n")
    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question:
            continue
        if question == "/quit":
            break
        if question == "/reset":
            history, session_id = [], str(uuid.uuid4())
            print("(history cleared, new session)\n")
            continue

        result = bot.answer(question, history, session_id=session_id, user_id=user_id,
                            metadata={"interface": "cli"})
        print(f"\nSnackBot: {result.answer}\n")
        if result.trace_id and config.TRACING == "full":
            print(f"  (trace {result.trace_id})\n")
        history += [{"role": "user", "content": question}, {"role": "assistant", "content": result.answer}]
    flush()  # PHASE 1: send any spans still waiting before the program exits


if __name__ == "__main__":
    main()
