//
//  AVPhoneFrameSink.m
//  Vision Camera v4 plugin registration glue.
//
//  Vision Camera registers frame-processor plugins at Obj-C +load time so
//  the plugin name is resolvable from the worklet thread before any
//  React component mounts. Swift classes can't expose +load, so we
//  declare a category on the Swift-imported class and call into the
//  Vision Camera registry from here. The Swift class itself is in
//  AVPhoneFrameSink.swift.
//
//  The bridging header is the Expo prebuild-generated
//  `<projectName>-Swift.h` file.
//

#import <VisionCamera/FrameProcessorPlugin.h>
#import <VisionCamera/FrameProcessorPluginRegistry.h>

@interface AVPhoneFrameSink : FrameProcessorPlugin
@end

@interface AVPhoneFrameSink (FrameProcessorPluginLoader)
@end

@implementation AVPhoneFrameSink (FrameProcessorPluginLoader)

+ (void)load {
    [FrameProcessorPluginRegistry addFrameProcessorPlugin:@"avPhoneFrameSink"
                                          withInitializer:^FrameProcessorPlugin* _Nonnull(VisionCameraProxyHolder* _Nonnull proxy, NSDictionary* _Nullable options) {
        return [[AVPhoneFrameSink alloc] initWithProxy:proxy withOptions:options];
    }];
}

@end
