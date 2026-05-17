
class HelloPlugin:
    name = "hello"

    async def on_load(self, config):
        self.loaded = True

    async def on_unload(self):
        self.unloaded = True

    async def execute_hook(self, hook, context):
        return f"{hook}:{context}"

plugin = HelloPlugin()
