package com.tvremoteweb;

import android.media.session.PlaybackState;
import android.os.IBinder;
import android.os.SystemClock;
import java.lang.reflect.Method;
import java.util.List;

/**
 * Seeks the active media session by a relative offset. Run as root via
 * app_process: players such as Stremio ignore KEYCODE_MEDIA_REWIND /
 * FAST_FORWARD but do accept a session seekTo.
 *
 *   mediactl status          print "pkg state positionMs" per session
 *   mediactl seek <deltaMs>  seek the playing (else paused) session
 */
public final class MediaCtl {
    public static void main(String[] args) throws Exception {
        if (args.length == 0) { System.out.println("usage: status | seek <deltaMs>"); System.exit(2); }
        IBinder b = (IBinder) Class.forName("android.os.ServiceManager")
                .getMethod("getService", String.class).invoke(null, "media_session");
        Object mgr = Class.forName("android.media.session.ISessionManager$Stub")
                .getMethod("asInterface", IBinder.class).invoke(null, b);
        List<?> tokens = (List<?>) find(mgr, "getSessions").invoke(mgr, null, 0);

        Object best = null; PlaybackState bestState = null; String bestPkg = null;
        for (Object token : tokens) {
            Object ctl = token.getClass().getMethod("getBinder").invoke(token);
            PlaybackState st = (PlaybackState) find(ctl, "getPlaybackState").invoke(ctl);
            String pkg = (String) find(ctl, "getPackageName").invoke(ctl);
            if (args[0].equals("status")) {
                System.out.println(pkg + " " + (st == null ? -1 : st.getState()) + " " + position(st));
                continue;
            }
            if (st == null || (st.getActions() & PlaybackState.ACTION_SEEK_TO) == 0) continue;
            int s = st.getState();
            if (s == PlaybackState.STATE_PLAYING || (s == PlaybackState.STATE_PAUSED && best == null)) {
                if (best == null || s == PlaybackState.STATE_PLAYING) { best = ctl; bestState = st; bestPkg = pkg; }
            }
        }
        if (!args[0].equals("seek")) return;
        if (best == null) { System.out.println("none"); System.exit(1); }
        long target = Math.max(0, position(bestState) + Long.parseLong(args[1]));
        find(best, "seekTo").invoke(best, "com.android.shell", target);
        System.out.println(bestPkg + " " + target);
    }

    private static long position(PlaybackState st) {
        if (st == null) return -1;
        long pos = st.getPosition();
        if (st.getState() == PlaybackState.STATE_PLAYING && st.getLastPositionUpdateTime() > 0) {
            pos += (long) ((SystemClock.elapsedRealtime() - st.getLastPositionUpdateTime()) * st.getPlaybackSpeed());
        }
        return pos;
    }

    private static Method find(Object o, String name) {
        for (Method m : o.getClass().getMethods()) if (m.getName().equals(name)) return m;
        throw new IllegalStateException("no method " + name);
    }
}
