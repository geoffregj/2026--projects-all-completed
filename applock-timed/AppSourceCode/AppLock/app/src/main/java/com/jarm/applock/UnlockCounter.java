package com.jarm.applock;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;

import java.util.Calendar;

// Counts screen unlocks for the "Today's Usage" screen. Registered
// dynamically (ACTION_USER_PRESENT is a protected implicit broadcast that
// can't be declared in the manifest since API 26) from the accessibility
// service's onServiceConnected - that service is already required to be
// running at all times for the app to function, so this adds no new
// always-on component, just one more case in a receiver that already exists
// for the app's core purpose. Registration is a no-op if already registered.
//
// Battery note: ACTION_USER_PRESENT is a system broadcast fired once per
// unlock, not a poll. This receiver does a single fast SharedPreferences
// write and returns - no wake lock, no loop, no measurable battery cost
// beyond the broadcast the system already sends regardless of whether we
// listen to it.
public class UnlockCounter {

    private static final String PREFS_NAME = "applock_stats";
    private static final String KEY_COUNT = "unlock_count";
    private static final String KEY_DATE = "unlock_count_date";

    private static boolean registered = false;
    private static final BroadcastReceiver receiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if (Intent.ACTION_USER_PRESENT.equals(intent.getAction())) {
                increment(context);
            }
        }
    };

    public static synchronized void registerIfNeeded(Context context) {
        if (registered) return;
        try {
            context.getApplicationContext().registerReceiver(receiver, new IntentFilter(Intent.ACTION_USER_PRESENT));
            registered = true;
        } catch (Exception e) {
            // If this ever fails, the unlock count just stays at 0/stale -
            // non-fatal, doesn't affect locking/suspending, which don't
            // depend on this class at all.
        }
    }

    // Same fix, same reasoning as AppLockSettings.currentDayId(): minSdk 24
    // without core library desugaring means java.time.LocalDate would crash
    // on a real API 24/25 device. Calendar-based instead.
    private static String currentDayId() {
        Calendar cal = Calendar.getInstance();
        return String.valueOf(cal.get(Calendar.YEAR) * 1000 + cal.get(Calendar.DAY_OF_YEAR));
    }

    private static void increment(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        String today = currentDayId();
        String storedDate = prefs.getString(KEY_DATE, "");
        int count = storedDate.equals(today) ? prefs.getInt(KEY_COUNT, 0) : 0;
        prefs.edit()
                .putString(KEY_DATE, today)
                .putInt(KEY_COUNT, count + 1)
                .apply();
    }

    // Returns today's unlock count, or 0 if the stored count is from a
    // previous day (rolls over lazily, same pattern AppLockSettings uses for
    // its own daily minutes - no background job needed to reset it).
    public static int getTodayCount(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        String today = currentDayId();
        String storedDate = prefs.getString(KEY_DATE, "");
        return storedDate.equals(today) ? prefs.getInt(KEY_COUNT, 0) : 0;
    }
}
