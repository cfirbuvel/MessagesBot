import asyncio


async def task(n):
    await asyncio.sleep(n)
    print(n)


async def main():
    for i in range(10):
        asyncio.create_task(task(i))
    return


if __name__ == '__main__':
    asyncio.run(main())