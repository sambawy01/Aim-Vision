/**
 * Phone frame-sink plugin — JS port of the TS version so Expo's
 * config-plugins runtime (plain `require()`, no TS transform) can load it
 * during `expo prebuild`.
 *
 * Keep this file in sync with `./withPhoneFrameSink.ts` until the project
 * is on a TS-aware Expo CLI build. The TS file is the canonical source for
 * humans + the test suite; this is the runtime entrypoint.
 *
 * Per ADR-0009 the plugin copies the native AVPhoneFrameSink Swift/Obj-C
 * + Kotlin sources into the prebuilt project so vision-camera frame
 * processors can call them via JSI.
 */
const path = require('node:path');
const fs = require('node:fs');
const {
  withDangerousMod,
  withXcodeProject,
} = require('@expo/config-plugins');

const IOS_GROUP_NAME = 'PhoneFrameSink';
const IOS_SOURCES = ['AVPhoneFrameSink.swift', 'AVPhoneFrameSink.m'];

function withIosSources(config) {
  return withDangerousMod(config, [
    'ios',
    async (mod) => {
      const projectRoot = mod.modRequest.projectRoot;
      const platformRoot = mod.modRequest.platformProjectRoot;
      const projectName = config.name ?? 'AIMVISION';
      const dest = path.join(platformRoot, projectName, IOS_GROUP_NAME);
      fs.mkdirSync(dest, { recursive: true });
      const src = path.join(projectRoot, 'plugins', 'phone-frame-sink', 'ios');
      for (const file of IOS_SOURCES) {
        const from = path.join(src, file);
        const to = path.join(dest, file);
        if (fs.existsSync(from)) {
          fs.copyFileSync(from, to);
        }
      }
      return mod;
    },
  ]);
}

function withIosXcodeRegistration(config) {
  return withXcodeProject(config, (mod) => {
    const project = mod.modResults;
    const projectName = config.name ?? 'AIMVISION';
    const groupPath = path.join(projectName, IOS_GROUP_NAME);
    let group = project.pbxGroupByName(IOS_GROUP_NAME);
    if (!group) {
      group = project.addPbxGroup([], IOS_GROUP_NAME, groupPath, '"<group>"');
      const mainGroup = project.getFirstProject().firstProject.mainGroup;
      project.addToPbxGroup(group.uuid, mainGroup);
    }
    // Xcode resolves file paths relative to the parent group. Passing the
    // group path again here would double it (was producing
    // `…/PhoneFrameSink/AIMVISION/PhoneFrameSink/<file>`).
    for (const file of IOS_SOURCES) {
      try {
        project.addSourceFile(file, { target: project.getFirstTarget().uuid }, group.uuid);
      } catch {
        // Already registered — ignore.
      }
    }
    return mod;
  });
}

module.exports = (config) => withIosXcodeRegistration(withIosSources(config));
