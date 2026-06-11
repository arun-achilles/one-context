"""
Interactive CLI for testing the agent locally.

Run:
    python -m agent.cli
"""
from dotenv import load_dotenv
load_dotenv()

from langchain_core.messages import HumanMessage
from agent.graph import get_graph


def main():
    graph = get_graph()
    history = []

    print("\nOne Context — Team Assistant")
    print("Type your question. Ctrl+C to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except KeyboardInterrupt:
            print("\nBye.")
            break

        if not user_input:
            continue

        history.append(HumanMessage(content=user_input))

        result = graph.invoke({"messages": history})
        response = result["messages"][-1].content

        print(f"\nAssistant: {response}\n")

        # Add assistant reply to history for multi-turn context
        history = result["messages"]


if __name__ == "__main__":
    main()
