/**
 * Unit tests for the Expo config plugin in `../withPhoneFrameSink.ts`.
 *
 * The functions exported by the plugin module each do one focused thing:
 * the file-system mutations and the AST-style text-rewrite of
 * MainApplication.kt + the Xcode .pbxproj. Those are pure functions
 * given their inputs; we mock fs for the copy step and stub a small
 * Xcode-project shape for the registration step.
 *
 * The actual `expo prebuild` integration is NOT exercised here — it
 * requires a generated `ios/` + `android/` tree. That's the manual
 * device-verification step documented in ADR-0009.
 */
import * as fs from 'fs';
import * as path from 'path';

// We partial-mock `fs` — only `mkdirSync` and `copyFileSync` get jest
// spies — because `@expo/config-plugins` (transitively imported by the
// plugin module under test) reads `fs.promises.readFile` at import time
// and dies if the entire module is wiped.
jest.mock('fs', () => {
  const actual = jest.requireActual<typeof import('fs')>('fs');
  return {
    ...actual,
    mkdirSync: jest.fn(),
    copyFileSync: jest.fn(),
  };
});

import {
  addIosSourcesToXcodeProject,
  copySource,
  destinationPath,
  injectPackageRegistration,
  pluginSourceFile,
} from '../withPhoneFrameSink';

describe('pluginSourceFile', () => {
  it('resolves an iOS source under plugins/phone-frame-sink/ios/', () => {
    const p = pluginSourceFile('ios', 'AVPhoneFrameSink.swift');
    expect(p).toContain(path.join('phone-frame-sink', 'ios', 'AVPhoneFrameSink.swift'));
  });

  it('resolves an Android source under plugins/phone-frame-sink/android/', () => {
    const p = pluginSourceFile('android', 'AVPhoneFrameSink.kt');
    expect(p).toContain(path.join('phone-frame-sink', 'android', 'AVPhoneFrameSink.kt'));
  });
});

describe('destinationPath', () => {
  it('iOS lands inside the named project subfolder under PhoneFrameSink/', () => {
    const p = destinationPath('/proj', 'AIMVISION', 'ios', 'AVPhoneFrameSink.swift');
    expect(p).toBe(
      path.join('/proj', 'ios', 'AIMVISION', 'PhoneFrameSink', 'AVPhoneFrameSink.swift'),
    );
  });

  it('Android lands inside the package directory tree', () => {
    const p = destinationPath('/proj', 'AIMVISION', 'android', 'AVPhoneFrameSink.kt');
    expect(p).toBe(
      path.join(
        '/proj',
        'android',
        'app',
        'src',
        'main',
        'java',
        'com',
        'aimvision',
        'app',
        'phoneframesink',
        'AVPhoneFrameSink.kt',
      ),
    );
  });
});

describe('copySource', () => {
  it('creates the destination directory and copies the file', () => {
    const mkdir = jest.spyOn(fs, 'mkdirSync').mockImplementation(() => undefined);
    const cp = jest.spyOn(fs, 'copyFileSync').mockImplementation(() => undefined);

    copySource('/src/file.swift', '/dest/dir/file.swift');

    expect(mkdir).toHaveBeenCalledWith('/dest/dir', { recursive: true });
    expect(cp).toHaveBeenCalledWith('/src/file.swift', '/dest/dir/file.swift');
  });
});

describe('injectPackageRegistration', () => {
  it('adds an import and a packages.add line when neither is present', () => {
    const before = [
      'package com.aimvision.app',
      '',
      'import android.app.Application',
      'import com.facebook.react.PackageList',
      '',
      'class MainApplication : Application(), ReactApplication {',
      '  override fun getPackages(): List<ReactPackage> {',
      '    val packages = PackageList(this).packages.toMutableList()',
      '    return packages',
      '  }',
      '}',
    ].join('\n');

    const after = injectPackageRegistration(before);
    expect(after).toContain('import com.aimvision.app.phoneframesink.AVPhoneFrameSinkPackage');
    expect(after).toContain('packages.add(AVPhoneFrameSinkPackage())');
    expect(after).toContain('return packages');
    // The packages.add line comes immediately before `return packages`.
    const addIdx = after.indexOf('packages.add(AVPhoneFrameSinkPackage())');
    const retIdx = after.indexOf('return packages');
    expect(addIdx).toBeLessThan(retIdx);
  });

  it('is idempotent — running twice does not duplicate imports or registrations', () => {
    const initial = [
      'package com.aimvision.app',
      '',
      'import android.app.Application',
      '',
      'override fun getPackages(): List<ReactPackage> {',
      '  val packages = PackageList(this).packages.toMutableList()',
      '  return packages',
      '}',
    ].join('\n');

    const once = injectPackageRegistration(initial);
    const twice = injectPackageRegistration(once);

    expect(twice).toBe(once);
    // And the registration only appears once.
    expect(once.match(/AVPhoneFrameSinkPackage\(\)/g)?.length).toBe(1);
  });

  it('falls back to "after the package declaration" when no imports exist', () => {
    const before = [
      'package com.aimvision.app',
      '',
      'class MainApplication : Application(), ReactApplication {',
      '  override fun getPackages(): List<ReactPackage> {',
      '    val packages = PackageList(this).packages.toMutableList()',
      '    return packages',
      '  }',
      '}',
    ].join('\n');

    const after = injectPackageRegistration(before);
    expect(after).toContain('import com.aimvision.app.phoneframesink.AVPhoneFrameSinkPackage');
  });
});

describe('addIosSourcesToXcodeProject', () => {
  // Build a minimal stub of the Xcode-project object that
  // `withXcodeProject` would hand us.
  function mkStubProject() {
    const calls: Record<string, unknown[][]> = {
      pbxGroupByName: [],
      addPbxGroup: [],
      addToPbxGroup: [],
      addSourceFile: [],
    };
    let groupExists = false;
    return {
      calls,
      project: {
        pbxGroupByName: (name: string) => {
          calls.pbxGroupByName.push([name]);
          return groupExists ? { uuid: 'existing-uuid' } : undefined;
        },
        addPbxGroup: (files: string[], name: string, path: string, sourceTree?: string) => {
          calls.addPbxGroup.push([files, name, path, sourceTree]);
          groupExists = true;
          return { uuid: 'group-uuid' };
        },
        getFirstProject: () => ({
          firstProject: { mainGroup: 'main-group-uuid' },
        }),
        addToPbxGroup: (file: unknown, parentUuid: string) => {
          calls.addToPbxGroup.push([file, parentUuid]);
        },
        addSourceFile: (filepath: string, options: object, groupUuid: string) => {
          calls.addSourceFile.push([filepath, options, groupUuid]);
        },
      },
    };
  }

  it('creates a PhoneFrameSink group and adds each source file to it', () => {
    const { project, calls } = mkStubProject();

    addIosSourcesToXcodeProject(project, ['A.swift', 'B.m']);

    expect(calls.addPbxGroup).toEqual([
      [['A.swift', 'B.m'], 'PhoneFrameSink', 'PhoneFrameSink', '"<group>"'],
    ]);
    expect(calls.addToPbxGroup).toEqual([[{ uuid: 'group-uuid' }, 'main-group-uuid']]);
    expect(calls.addSourceFile).toHaveLength(2);
    expect(calls.addSourceFile[0][0]).toBe(path.join('PhoneFrameSink', 'A.swift'));
    expect(calls.addSourceFile[1][0]).toBe(path.join('PhoneFrameSink', 'B.m'));
  });

  it('is idempotent — a second invocation finds the existing group and skips', () => {
    const { project, calls } = mkStubProject();
    addIosSourcesToXcodeProject(project, ['A.swift']);
    addIosSourcesToXcodeProject(project, ['A.swift']);

    // addPbxGroup only fired once; second pass short-circuited on the
    // group-exists check.
    expect(calls.addPbxGroup).toHaveLength(1);
    expect(calls.addSourceFile).toHaveLength(1);
  });
});
