
import asyncio

from backend.providers.manager import (
    provider_manager,
    ProviderError,
)


async def main():

    messages = [
        {
            "role": "system",
            "content": "You are Jarvis, a helpful AI assistant."
        },
        {
            "role": "user",
            "content": "Introduce yourself in one sentence."
        }
    ]

    provider = provider_manager.default_provider
    model = provider_manager.get_model(provider)

    print(f"Testing provider: {provider}")
    print(f"Testing model: {model}")
    print("-" * 40)

    try:
        response = await provider_manager.ask(
            messages=messages,
            provider=provider,
            model=model,
        )

        print("Jarvis response:")
        print(response)

    except ProviderError as error:
        print(f"Provider error: {error}")


if __name__ == "__main__":
    asyncio.run(main())
