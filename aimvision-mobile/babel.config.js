module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    plugins: ['react-native-reanimated/plugin'],
    overrides: [
      {
        // `babel-preset-expo` in test env doesn't include `@babel/preset-flow`,
        // so RN's Flow-typed vendor files (EventEmitter.js, error-guard.js,
        // etc.) fail to parse under jest. Scope the Flow preset to file paths
        // containing `react-native` so it never touches our TS project source.
        test: /react-native/,
        presets: ['@babel/preset-flow'],
      },
    ],
  };
};
