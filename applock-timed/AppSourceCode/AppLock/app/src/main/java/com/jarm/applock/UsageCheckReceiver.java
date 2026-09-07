package com.jarm.applock;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.app.admin.DevicePolicyManager;
import android.app.usage.UsageStats;
import android.app.usage.UsageStatsManager;
import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.SystemClock;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

// Replaces a continuously-running watcher: this fires on a timer (default
// every 30 minutes - see AppLockSettings.CHECK_INTERVAL_MINUTES), asks
// UsageStatsManager how much foreground time every app has racked up today,
// and suspends/unsuspends packages at the OS level with
// DevicePolicyManager.setPackagesSuspended() accordingly. Nothing runs in
// between checks - no service, no listener, no wake lock held.
public class UsageCheckReceiver extends BroadcastReceiver {

    private static final String ACTION_CHECK = "com.jarm.applock.action.USAGE_CHECK";
    private static final int REQUEST_CODE = 4200;

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        if (Intent.ACTION_BOOT_COMPLETED.equals(action) || ACTION_CHECK.equals(action) || action == null) {
            runCheck(context);
        }
        scheduleNext(context);
    }

    private void runCheck(Context context) {
        AppLockSettings settings = loadSettings(context);
        settings.rollOverIfNewDay();

        UsageStatsManager usm = (UsageStatsManager) context.getSystemService(Context.USAGE_STATS_SERVICE);
        PackageManager pm = context.getPackageManager();
        DevicePolicyManager dpm = (DevicePolicyManager) context.getSystemService(Context.DEVICE_POLICY_SERVICE);
        ComponentName admin = new ComponentName(context, DeviceAdminReceiverForDeviceOwner.class);

        String selfPackage = context.getPackageName();
        String launcherPackage = getDefaultLauncherPackage(context);
        String inputMethodPackage = getDefaultInputMethodPackage(context);

        Calendar startOfDay = Calendar.getInstance();
        startOfDay.set(Calendar.HOUR_OF_DAY, 0);
        startOfDay.set(Calendar.MINUTE, 0);
        startOfDay.set(Calendar.SECOND, 0);
        startOfDay.set(Calendar.MILLISECOND, 0);
        long now = System.currentTimeMillis();

        List<UsageStats> statsList = usm.queryUsageStats(UsageStatsManager.INTERVAL_DAILY, startOfDay.getTimeInMillis(), now);

        HashMap<String, Integer> minutesPerPackage = new HashMap<String, Integer>();
        Set<String> socialPackages = new HashSet<String>();

        if (statsList != null) {
            for (UsageStats stats : statsList) {
                String pkg = stats.getPackageName();
                if (pkg == null) continue;
                if (isExempt(pkg, selfPackage, launcherPackage, inputMethodPackage)) continue;
                long ms = stats.getTotalTimeInForeground();
                if (ms <= 0) continue;
                int minutes = (int) (ms / 60000);
                if (minutes <= 0) continue;
                minutesPerPackage.put(pkg, minutes);
                if (AppCategoryHelper.isSocialApp(context, pkg)) {
                    socialPackages.add(pkg);
                }
            }
        }

        settings.syncUsageFromSystem(minutesPerPackage, socialPackages);
        saveSettings(context, settings);

        boolean overGlobal = settings.isOverGlobalDailyLimit();
        boolean overSocial = settings.isOverSocialDailyLimit();

        ArrayList<String> toSuspend = new ArrayList<String>();
        ArrayList<String> toUnsuspend = new ArrayList<String>();

        List<ApplicationInfo> installedApps = pm.getInstalledApplications(0);
        for (ApplicationInfo app : installedApps) {
            String pkg = app.packageName;
            if (isExempt(pkg, selfPackage, launcherPackage, inputMethodPackage)) continue;

            boolean isSocial = AppCategoryHelper.isSocialApp(context, pkg);
            boolean shouldBeSuspended = overGlobal || (isSocial && overSocial) || settings.isAppPackageNameLocked(pkg);

            boolean currentlySuspended;
            try {
                currentlySuspended = dpm.isPackageSuspended(admin, pkg);
            } catch (Exception e) {
                continue; // package can't be suspended (e.g. some system apps) - skip
            }

            if (shouldBeSuspended && !currentlySuspended) {
                toSuspend.add(pkg);
            } else if (!shouldBeSuspended && currentlySuspended) {
                toUnsuspend.add(pkg);
            }
        }

        if (!toSuspend.isEmpty()) {
            try {
                dpm.setPackagesSuspended(admin, toSuspend.toArray(new String[0]), true);
            } catch (Exception e) {
            }
        }
        if (!toUnsuspend.isEmpty()) {
            try {
                dpm.setPackagesSuspended(admin, toUnsuspend.toArray(new String[0]), false);
            } catch (Exception e) {
            }
        }
    }

    private boolean isExempt(String pkg, String selfPackage, String launcherPackage, String inputMethodPackage) {
        if (pkg == null) return true;
        if (pkg.equals(selfPackage)) return true;
        if (pkg.equals("android")) return true;
        if (pkg.equals("com.android.systemui")) return true;
        if (pkg.equals(launcherPackage)) return true;
        if (inputMethodPackage != null && pkg.equals(inputMethodPackage)) return true;
        // Never suspend Settings - you'd have no way to see status or reboot cleanly
        if (pkg.equals("com.android.settings")) return true;
        return false;
    }

    private String getDefaultLauncherPackage(Context context) {
        PackageManager pm = context.getPackageManager();
        Intent intent = new Intent(Intent.ACTION_MAIN);
        intent.addCategory(Intent.CATEGORY_HOME);
        android.content.pm.ResolveInfo resolveInfo = pm.resolveActivity(intent, PackageManager.MATCH_DEFAULT_ONLY);
        if (resolveInfo != null && resolveInfo.activityInfo != null) {
            return resolveInfo.activityInfo.packageName;
        }
        return "";
    }

    private String getDefaultInputMethodPackage(Context context) {
        String value = android.provider.Settings.Secure.getString(context.getContentResolver(), "default_input_method");
        if (value == null) return null;
        int slash = value.indexOf("/");
        return slash != -1 ? value.substring(0, slash) : value;
    }

    private AppLockSettings loadSettings(Context context) {
        try {
            FileInputStream file = new FileInputStream(context.getDataDir() + "/dataa");
            ObjectInputStream in = new ObjectInputStream(file);
            AppLockSettings settings = (AppLockSettings) in.readObject();
            in.close();
            file.close();
            return settings;
        } catch (Exception e) {
            return new AppLockSettings();
        }
    }

    private void saveSettings(Context context, AppLockSettings settings) {
        try {
            FileOutputStream file = new FileOutputStream(context.getDataDir() + "/dataa");
            ObjectOutputStream out = new ObjectOutputStream(file);
            out.writeObject(settings);
            out.close();
            file.close();
        } catch (Exception e) {
        }
    }

    // Schedules (or reschedules) the next check. Device Owner apps are
    // exempt from the API 31+ exact-alarm permission restriction, so this
    // works without any user-facing "allow exact alarms" prompt.
    public static void scheduleNext(Context context) {
        AlarmManager am = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        Intent intent = new Intent(context, UsageCheckReceiver.class);
        intent.setAction(ACTION_CHECK);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0);
        PendingIntent pendingIntent = PendingIntent.getBroadcast(context, REQUEST_CODE, intent, flags);
        long triggerAt = SystemClock.elapsedRealtime() + AppLockSettings.CHECK_INTERVAL_MINUTES * 60 * 1000;
        try {
            am.setExactAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP, triggerAt, pendingIntent);
        } catch (Exception e) {
            am.set(AlarmManager.ELAPSED_REALTIME_WAKEUP, triggerAt, pendingIntent);
        }
    }
}
