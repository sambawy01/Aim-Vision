/**
 * Expo config plugin — phone-capture slice 3b native frame-processor plugin
 * (ADR-0009 — docs/adr/0009-phone-capture-dev-backend.md).
 *
 * Runs at `expo prebuild` time. Copies the in-tree native sources from
 * `plugins/phone-frame-sink/{ios,android}/` into the generated native
 * projects, adds the iOS files to the Xcode project, and registers the
 * Android package in MainApplication.
 *
 * Authored as CommonJS JavaScript so a fresh clone can `expo prebuild`
 * without any compile step — Expo's plugin resolver does not load `.ts`
 * files by default, so a TS source would need a tsc/postinstall hook.
 * The trade-off is loose JS types in the plugin itself; the native
 * surface it touches is exercised end-to-end at prebuild time and by the
 * unit tests in `__tests__/`.
 */

'use strict';

const { withDangerousMod, withMainApplication, withXcodeProject } = require('@expo/config-plugins');
const fs = require('fs');
const path = require('path');

const IOS_GROUP_NAME = 'PhoneFrameSink';
const ANDROID_PACKAGE = 'com.aimvision.app.phoneframesink';
const ANDROID_PACKAGE_CLASS = 'AVPhoneFrameSinkPackage';

const IOS_SOURCES = [
  'AVPhoneFrameSink.swift',
  'AVPhoneFrameSink.m',
  // Slice 3c — Swift bridge to the Rust C ABI in `aimvision-camera-phone`.
  // `dlsym`-based; compiles even when the Rust static library isn't yet linked
  // into the Xcode target, and the bridge reports unavailable at runtime.
  'AVPhoneFrameSinkBridge.swift',
];

const ANDROID_SOURCES = [
  'AVPhoneFrameSink.kt',
  'AVPhoneFrameSinkPackage.kt',
  // Slice 3c — Kotlin bridge with `System.loadLibrary` + `external fun`
  // declarations. The JNI C shim is a follow-up sub-slice; until it ships,
  // the bridge reports unavailable at runtime.
  'AVPhoneFrameSinkBridge.kt',
];

/** Absolute path to a native source shipped alongside this plugin. */
function pluginSourceFile(platform, filename) {
  return path.join(__dirname, platform, filename);
}

/**
 * Destination path for a native source inside the generated Expo output.
 *  - iOS:     <projectRoot>/ios/<projectName>/PhoneFrameSink/<file>
 *  - Android: <projectRoot>/android/app/src/main/java/com/aimvision/app/phoneframesink/<file>
 */
function destinationPath(projectRoot, projectName, platform, filename) {
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

function copySource(srcAbs, destAbs) {
  fs.mkdirSync(path.dirname(destAbs), { recursive: true });
  fs.copyFileSync(srcAbs, destAbs);
}

/**
 * Insert `import …AVPhoneFrameSinkPackage` + `packages.add(...)` into
 * MainApplication.kt. Idempotent: re-running won't duplicate.
 */
function injectPackageRegistration(mainApplication) {
  if (mainApplication.includes(ANDROID_PACKAGE_CLASS)) {
    return mainApplication;
  }
  const importLine = `import ${ANDROID_PACKAGE}.${ANDROID_PACKAGE_CLASS}`;
  let next = mainApplication;
  const importMatch = next.match(/(\n)((?:import [^\n]+\n)+)/);
  if (importMatch && importMatch.index !== undefined) {
    const insertAt = importMatch.index + importMatch[0].length;
    next = `${next.slice(0, insertAt)}${importLine}\n${next.slice(insertAt)}`;
  } else {
    next = next.replace(/^(package\s+[^\n]+\n)/m, `$1\n${importLine}\n`);
  }
  next = next.replace(
    /(return packages\b)/,
    `packages.add(${ANDROID_PACKAGE_CLASS}())\n      $1`,
  );
  return next;
}

/**
 * Add the iOS source files to the Xcode project under a new
 * "PhoneFrameSink" group inside the app target. Idempotent.
 */
function addIosSourcesToXcodeProject(xcodeProject, iosSources) {
  if (xcodeProject.pbxGroupByName(IOS_GROUP_NAME)) {
    return;
  }
  const group = xcodeProject.addPbxGroup(
    iosSources.slice(),
    IOS_GROUP_NAME,
    IOS_GROUP_NAME,
    '"<group>"',
  );
  xcodeProject.addToPbxGroup(group, xcodeProject.getFirstProject().firstProject.mainGroup);
  for (const src of iosSources) {
    xcodeProject.addSourceFile(
      path.join(IOS_GROUP_NAME, src),
      { target: undefined },
      group.uuid,
    );
  }
}

/** The plugin entry point. Hooked up via `app.json`'s `plugins` array. */
function withPhoneFrameSink(config) {
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
    addIosSourcesToXcodeProject(cfg.modResults, IOS_SOURCES);
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
}

module.exports = withPhoneFrameSink;
module.exports.default = withPhoneFrameSink;
// Named exports kept for the unit tests in `__tests__/withPhoneFrameSink.test.ts`.
module.exports.pluginSourceFile = pluginSourceFile;
module.exports.destinationPath = destinationPath;
module.exports.copySource = copySource;
module.exports.injectPackageRegistration = injectPackageRegistration;
module.exports.addIosSourcesToXcodeProject = addIosSourcesToXcodeProject;
