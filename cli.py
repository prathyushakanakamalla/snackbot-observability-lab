"""Chat with SnackBot in the terminal.  Run:  python cli.py   (commands: /reset, /quit)"""
from snackbot.agent import SnackBot


def main():
    bot, history = SnackBot(), []
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
            history = []
            print("(history cleared)\n")
            continue

        result = bot.answer(question, history)
        print(f"\nSnackBot: {result.answer}\n")
        history += [{"role": "user", "content": question}, {"role": "assistant", "content": result.answer}]


if __name__ == "__main__":
    main()
