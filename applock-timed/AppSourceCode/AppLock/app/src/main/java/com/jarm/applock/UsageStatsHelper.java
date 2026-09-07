package com.jarm.applock;

import android.app.usage.UsageStats;
import android.app.usage.UsageStatsManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;

import java.util.ArrayList;
import java.util.Calendar;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

// One-shot, on-demand usage query used by TodayUsageActivity (the "Today's
// Usage" ring screen). Deliberately separate from UsageCheckReceiver's own
// query rather than a shared refactor of it: UsageCheckReceiver is the
// already-working 30-minute background check that suspends apps over their
// budget, and it's not touched here so nothing about that path risks
// regressing. This class only runs when a user actually opens the usage
// screen - it holds no state, schedules nothing, and does no work in the
// background.
public class UsageStatsHelper {

    // One bucket of usage, either a real app or the synthetic "Other" catch-all.
    public static class UsageBucket {
        public final String label;
        public final int minutes;
        public UsageBucket(String label, int minutes) {
            this.label = label;
            this.minutes = minutes;
        }
    }

    // Same exemption list as UsageCheckReceiver (self, launcher, input method,
    // systemui, Settings) so the ring matches what actually counts toward the
    // daily budget rather than including apps that can never be suspended.
    private static boolean isExempt(Context context, String pkg, String selfPackage, String launcherPackage, String inputMethodPackage) {
        if (pkg == null) return true;
        if (pkg.equals(selfPackage)) return true;
        if (pkg.equals("android")) return true;
        if (pkg.equals("com.android.systemui")) return true;
        if (pkg.equals(launcherPackage)) return true;
        if (inputMethodPackage != null && pkg.equals(inputMethodPackage)) return true;
        if (pkg.equals("com.android.settings")) return true;
        return false;
    }

    private static String getDefaultLauncherPackage(Context context) {
        PackageManager pm = context.getPackageManager();
        Intent intent = new Intent(Intent.ACTION_MAIN);
        intent.addCategory(Intent.CATEGORY_HOME);
        ResolveInfo resolveInfo = pm.resolveActivity(intent, PackageManager.MATCH_DEFAULT_ONLY);
        if (resolveInfo != null && resolveInfo.activityInfo != null) {
            return resolveInfo.activityInfo.packageName;
        }
        return "";
    }

    private static String getDefaultInputMethodPackage(Context context) {
        String value = android.provider.Settings.Secure.getString(context.getContentResolver(), "default_input_method");
        if (value == null) return null;
        int slash = value.indexOf("/");
        return slash != -1 ? value.substring(0, slash) : value;
    }

    // Raw package -> minutes-used-today map, since midnight, exemptions applied.
    public static Map<String, Integer> getMinutesPerAppToday(Context context) {
        UsageStatsManager usm = (UsageStatsManager) context.getSystemService(Context.USAGE_STATS_SERVICE);
        HashMap<String, Integer> minutesPerPackage = new HashMap<>();
        if (usm == null) return minutesPerPackage;

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
        if (statsList == null) return minutesPerPackage;

        for (UsageStats stats : statsList) {
            String pkg = stats.getPackageName();
            if (isExempt(context, pkg, selfPackage, launcherPackage, inputMethodPackage)) continue;
            long ms = stats.getTotalTimeInForeground();
            if (ms <= 0) continue;
            int minutes = (int) (ms / 60000);
            if (minutes <= 0) continue;
            minutesPerPackage.put(pkg, minutes);
        }
        return minutesPerPackage;
    }

    // Top N apps by minutes, everything else folded into a single "Other"
    // bucket - same convention Android's own Digital Wellbeing ring uses, and
    // it keeps the ring/legend readable instead of growing with every app
    // that had a few seconds of foreground time today.
    public static List<UsageBucket> topBucketsWithOther(Context context, Map<String, Integer> minutesPerPackage, int topN) {
        List<Map.Entry<String, Integer>> entries = new ArrayList<>(minutesPerPackage.entrySet());
        entries.sort(new Comparator<Map.Entry<String, Integer>>() {
            @Override
            public int compare(Map.Entry<String, Integer> a, Map.Entry<String, Integer> b) {
                return b.getValue() - a.getValue();
            }
        });

        PackageManager pm = context.getPackageManager();
        List<UsageBucket> buckets = new ArrayList<>();
        int otherMinutes = 0;
        for (int i = 0; i < entries.size(); i++) {
            Map.Entry<String, Integer> entry = entries.get(i);
            if (i < topN) {
                String label = entry.getKey();
                try {
                    label = pm.getApplicationLabel(pm.getApplicationInfo(entry.getKey(), 0)).toString();
                } catch (Exception e) {
                    // keep package name as fallback label
                }
                buckets.add(new UsageBucket(label, entry.getValue()));
            } else {
                otherMinutes += entry.getValue();
            }
        }
        if (otherMinutes > 0) {
            buckets.add(new UsageBucket("Other", otherMinutes));
        }
        return buckets;
    }

    public static int totalMinutes(Map<String, Integer> minutesPerPackage) {
        int total = 0;
        for (int m : minutesPerPackage.values()) total += m;
        return total;
    }
}
