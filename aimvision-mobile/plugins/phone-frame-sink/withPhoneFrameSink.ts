/**
 * Expo config plugin — phone-capture slice 3b native frame-processor plugin
 * ([ADR-0009](../../../docs/adr/0009-phone-capture-dev-backend.md)).
 *
 * Runs at `expo prebuild` time. Copies the in-tree native sources from
 * `plugins/phone-frame-sink/{ios,android}/` into the generated native
 * projects, adds the iOS files to the Xcode project, and registers the
 * Android package in `MainApplication`.
 *
 * # Why this is a *local* config plugin, not a published npm package
 *
 * The frame-sink plugin is internal-dev-only per ADR-0009 §17.3 — we don't
 * want it shipping to anyone else. Co-locating the native sources + the
 * config plugin in the app repo keeps the version lock-step (the Swift /
 * Kotlin contract evolves alongside the JS worklet that invokes it) and
 * avoids the per-package release churn that comes with publishing.
 *
 * # CI-verifiable surface
 *
 * Only the TypeScript here. Native compilation happens at
 * `expo prebuild --clean && expo run:ios|android` on a developer machine;
 * CI runs jest + typecheck + lint but does NOT prebuild. Tests cover the
 * file-copy + Xcode-project + MainApplication mutations in isolation via
 * mocked filesystem + mocked config objects.
 */

import {
  type ConfigPlugin,
  withDangerousMod,
  withMainApplication,
  withXcodeProject,
} from '@expo/config-plugins';
import * as fs from 'fs';
import * as path from 'path';

const PLUGIN_DIR_NAME = 'phone-frame-sink';
const IOS_GROUP_NAME = 'PhoneFrameSink';
const ANDROID_PACKAGE = 'com.aimvision.app.phoneframesink';
const ANDROID_PACKAGE_CLASS = 'AVPhoneFrameSinkPackage';

const IOS_SOURCES = [
  'AVPhoneFrameSink.swift',
  'AVPhoneFrameSink.m',
  // Slice 3c — Swift bridge to the Rust C ABI in `aimvision-camera-phone`.
  // `dlsym`-based; the file compiles even when the Rust static library
  // isn't yet linked into the Xcode target, and the bridge reports
  // unavailable at runtime in that case.
  'AVPhoneFrameSinkBridge.swift',
] as const;
const ANDROID_SOURCES = [
  'AVPhoneFrameSink.kt',
  'AVPhoneFrameSinkPackage.kt',
  // Slice 3c — Kotlin bridge with `System.loadLibrary` + `external fun`
  // declarations. The JNI C shim itself is a follow-up sub-slice; until
  // it ships the bridge reports unavailable at runtime.
  'AVPhoneFrameSinkBridge.kt',
] as const;

/** Resolve the absolute path to a native source shipped alongside this
 * plugin. Exported for the unit test. */
export function pluginSourceFile(platform: 'ios' | 'android', filename: string): string {
  return path.join(__dirname, platform, filename);
}

/** Compute the destination path for a native source inside the generated
 * Expo prebuild output. Exported for the unit test.
 *
 * - iOS files land in `<projectRoot>/ios/<projectName>/PhoneFrameSink/<file>`
 * - Android files land in `<projectRoot>/android/app/src/main/java/com/aimvision/app/phoneframesink/<file>`
 */
export function destinationPath(
  projectRoot: string,
  projectName: string,
  platform: 'ios' | 'android',
  filename: string,
): string {
  if (platform === 'ios') {
    return path.join(projectRoot, 'ios', projectName, IOS_GROUP_NAME, filename);
  }
  return path.join(
    projectRoot,
    'android',
    'app',
    'src',
    'main',
    'java',
    ...ANDROID_PACKAGE.split('.'),
    filename,
  );
}

/** Copy a single source file with directory creation. Exported for the
 * unit test so we can drive it with mocked fs. */
export function copySource(srcAbs: string, destAbs: string): void {
  fs.mkdirSync(path.dirname(destAbs), { recursive: true });
  fs.copyFileSync(srcAbs, destAbs);
}

/** Insert a `new AVPhoneFrameSinkPackage()` line into the
 * `getPackages()` block of MainApplication.kt. Idempotent: if the line
 * already exists we return the source unchanged so re-runs don't duplicate
 * imports. Exported for the unit test. */
export function injectPackageRegistration(mainApplication: string): string {
  if (mainApplication.includes(ANDROID_PACKAGE_CLASS)) {
    return mainApplication;
  }
  const importLine = `import ${ANDROID_PACKAGE}.${ANDROID_PACKAGE_CLASS}`;
  // 1. Add the import — after the last existing import statement so we
  //    don't risk landing above the package declaration.
  let next = mainApplication;
  const importMatch = next.match(/(\n)((?:import [^\n]+\n)+)/);
  if (importMatch && importMatch.index !== undefined) {
    const insertAt = importMatch.index + importMatch[0].length;
    next = `${next.slice(0, insertAt)}${importLine}\n${next.slice(insertAt)}`;
  } else {
    // No existing imports? Fall back to inserting right after the
    // `package` declaration.
    next = next.replace(/^(package\s+[^\n]+\n)/m, `$1\n${importLine}\n`);
  }
  // 2. Inject `packages.add(AVPhoneFrameSinkPackage())` into the
  //    getPackages() block. The canonical RN template uses
  //    `PackageList(this).packages` -> `val packages = ... .toMutableList()`
  //    so we add to the mutable list right before `return packages`.
  next = next.replace(/(return packages\b)/, `packages.add(${ANDROID_PACKAGE_CLASS}())\n      $1`);
  return next;
}

/** Add the iOS source files to the Xcode project as a new "PhoneFrameSink"
 * group inside the app target. Exported for the unit test.
 *
 * `xcodeProject` is the xcode-pbxproj parsed project from xcode npm
 * package (what `withXcodeProject` hands us). We use the same helpers
 * the rest of the Expo plugin ecosystem uses. */
type XcodeProjectLike = {
  pbxGroupByName(name: string): unknown;
  addPbxGroup(
    files: string[],
    name: string,
    path: string,
    sourceTree?: string,
  ): {
    uuid: string;
  };
  getFirstProject(): { firstProject: { mainGroup: string } };
  addToPbxGroup(file: { uuid: string }, parentUuid: string): void;
  addSourceFile(filepath: string, options?: object, groupUuid?: string): unknown;
};

export function addIosSourcesToXcodeProject(
  xcodeProject: XcodeProjectLike,
  iosSources: readonly string[],
): void {
  // Idempotent: if the group already exists, the plugin has already run.
  if (xcodeProject.pbxGroupByName(IOS_GROUP_NAME)) {
    return;
  }
  const group = xcodeProject.addPbxGroup(
    iosSources.slice(),
    IOS_GROUP_NAME,
    IOS_GROUP_NAME,
    '"<group>"',
  );
  // Slot the new group under the main project group.
  xcodeProject.addToPbxGroup(group, xcodeProject.getFirstProject().firstProject.mainGroup);
  for (const src of iosSources) {
    xcodeProject.addSourceFile(path.join(IOS_GROUP_NAME, src), { target: undefined }, group.uuid);
  }
}

/** The plugin entry point. Hooked up via `app.json`'s `plugins` array. */
const withPhoneFrameSink: ConfigPlugin = (config) => {
  // 1. Copy iOS sources into the generated project tree.
  config = withDangerousMod(config, [
    'ios',
    async (cfg) => {
      const projectName = cfg.modRequest.projectName ?? cfg.name ?? 'AIMVISION';
      for (const file of IOS_SOURCES) {
        copySource(
          pluginSourceFile('ios', file),
          destinationPath(cfg.modRequest.projectRoot, projectName, 'ios', file),
        );
      }
      return cfg;
    },
  ]);

  // 2. Register iOS sources in the Xcode project (.pbxproj).
  config = withXcodeProject(config, (cfg) => {
    addIosSourcesToXcodeProject(cfg.modResults as unknown as XcodeProjectLike, IOS_SOURCES);
    return cfg;
  });

  // 3. Copy Android sources into the generated project tree.
  config = withDangerousMod(config, [
    'android',
    async (cfg) => {
      const projectName = cfg.modRequest.projectName ?? cfg.name ?? 'AIMVISION';
      for (const file of ANDROID_SOURCES) {
        copySource(
          pluginSourceFile('android', file),
          destinationPath(cfg.modRequest.projectRoot, projectName, 'android', file),
        );
      }
      return cfg;
    },
  ]);

  // 4. Register the Android package in MainApplication.kt.
  config = withMainApplication(config, (cfg) => {
    cfg.modResults.contents = injectPackageRegistration(cfg.modResults.contents);
    return cfg;
  });

  return config;
};

export default withPhoneFrameSink;
