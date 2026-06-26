import { defineConfig } from "@trigger.dev/sdk/v3";
import { pythonExtension } from "@trigger.dev/python/extension";
import { ffmpeg } from "@trigger.dev/build/extensions/core";

const project = process.env.TRIGGER_PROJECT_REF;

if (!project) {
  throw new Error("TRIGGER_PROJECT_REF обязателен для Trigger.dev build");
}

export default defineConfig({
  project,
  maxDuration: 7200,
  dirs: ["./src/trigger"],
  build: {
    extensions: [
      pythonExtension({
        scripts: ["./src/**/*.py", "./scripts/**/*.py"],
        requirementsFile: "./requirements.txt",
      }),
      ffmpeg(),
    ],
  },
});
