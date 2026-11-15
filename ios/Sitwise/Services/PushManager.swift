import UIKit
import UserNotifications

/// APNs: ask permission, register, and give the device token to the server so it can push this
/// phone (the system notification is what vibrates it when the app isn't in the foreground).
final class PushManager: NSObject, UNUserNotificationCenterDelegate {
    static let shared = PushManager()
    private var deviceToken: String?

    func requestPermissionAndRegister() {
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        center.requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            guard granted else { return }
            DispatchQueue.main.async { UIApplication.shared.registerForRemoteNotifications() }
        }
    }

    func didRegister(deviceToken data: Data) {
        deviceToken = data.map { String(format: "%02x", $0) }.joined()
        syncToServer()
    }

    /// Sends the token once we have both the token and a paired device token (either may arrive first).
    func syncToServer() {
        guard let token = deviceToken, Keychain.token != nil else { return }
        Task { try? await APIClient.shared.registerAPNs(token: token, sandbox: Config.apnsSandbox) }
    }

    // Show the banner + sound even while the app is open (the monitor also does a haptic).
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }
}

final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = PushManager.shared
        return true
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        PushManager.shared.didRegister(deviceToken: deviceToken)
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        // Expected on the simulator and without the Push Notifications capability / a paid team.
        print("APNs registration failed: \(error.localizedDescription)")
    }
}
