import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { isDeepStrictEqual } from "node:util";
import { fileURLToPath } from "node:url";

const project = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const developmentDesktop = join(project, "..", "RLMResearchPlanner");
const publicDesktop = join(project, "..", "..");
const desktop = existsSync(join(developmentDesktop, "pyproject.toml"))
  ? developmentDesktop
  : publicDesktop;
const source = join(desktop, "data", "research", "catalog.json");
const destination = join(project, "data", "research", "catalog.json");
const datasetSource = join(desktop, "dataset", "generated");
const datasetDestination = join(project, "data", "research-dataset");
const localeDirectory = join(desktop, "resources", "i18n");
const castleSource = join(desktop, "data", "buildings", "castle_catalog.json");
const castleDestination = join(project, "data", "buildings", "castle_catalog.json");
const talentSource = join(desktop, "data", "talents", "catalog.json");
const talentDestination = join(project, "data", "talents", "catalog.json");

function copyFileIfChanged(sourcePath, destinationPath) {
  try {
    const sourceData = readFileSync(sourcePath);
    const destinationData = readFileSync(destinationPath);
    if (sourceData.equals(destinationData)) return;
    if (
      sourcePath.endsWith(".json")
      && destinationPath.endsWith(".json")
      && isDeepStrictEqual(
        JSON.parse(sourceData.toString("utf8")),
        JSON.parse(destinationData.toString("utf8")),
      )
    ) return;
  } catch {
    // The destination may not exist yet.
  }
  copyFileSync(sourcePath, destinationPath);
}

function copyDirectoryFiles(sourceDirectory, destinationDirectory) {
  mkdirSync(destinationDirectory, { recursive: true });
  for (const entry of readdirSync(sourceDirectory, { withFileTypes: true })) {
    const sourcePath = join(sourceDirectory, entry.name);
    const destinationPath = join(destinationDirectory, entry.name);
    if (entry.isDirectory()) {
      copyDirectoryFiles(sourcePath, destinationPath);
    } else if (entry.isFile()) {
      copyFileIfChanged(sourcePath, destinationPath);
    }
  }
}

mkdirSync(dirname(destination), { recursive: true });
copyFileIfChanged(source, destination);
copyDirectoryFiles(datasetSource, datasetDestination);
copyDirectoryFiles(localeDirectory, join(project, "data", "i18n"));
mkdirSync(dirname(castleDestination), { recursive: true });
copyFileIfChanged(castleSource, castleDestination);
mkdirSync(dirname(talentDestination), { recursive: true });
copyFileIfChanged(talentSource, talentDestination);
process.stdout.write(`Synced ${source} -> ${destination}\n`);
process.stdout.write(`Synced ${datasetSource} -> ${datasetDestination}\n`);
process.stdout.write(`Synced locale manifest and bundled language packs\n`);
process.stdout.write(`Synced ${castleSource} -> ${castleDestination}\n`);
process.stdout.write(`Synced ${talentSource} -> ${talentDestination}\n`);
