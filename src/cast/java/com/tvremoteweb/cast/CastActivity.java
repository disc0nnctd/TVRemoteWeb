package com.tvremoteweb.cast;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.SpannableString;
import android.text.Spanned;
import android.text.style.ForegroundColorSpan;
import android.text.style.RelativeSizeSpan;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

// Home-screen "Cast" tile: one picker for the projector's built-in receivers.
// It talks to the module's cast.cgi over loopback, which trusts 127.0.0.1, so
// no token is needed and nothing keeps running once the picker closes.
public class CastActivity extends Activity {
    static final String[][] CHOICES = {
        {"miracast", "Android / Windows", "Miracast · remote pauses while casting"},
        {"airplay",  "iPhone / Mac",      "AirPlay · remote keeps working"},
        {"dlna",     "Media app",         "DLNA · lowest load"},
        {"stop",     "Stop casting",      "Release receivers, restore Wi-Fi"},
    };
    final Handler main = new Handler(Looper.getMainLooper());
    final Button[] buttons = new Button[CHOICES.length];
    TextView status;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setBackgroundColor(Color.rgb(11, 13, 16));
        root.setPadding(dp(48), dp(32), dp(48), dp(32));

        TextView title = text("Cast to this projector", 30, Color.WHITE);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        root.addView(title);

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams rowLp = new LinearLayout.LayoutParams(-1, -2);
        rowLp.topMargin = dp(28);
        root.addView(row, rowLp);

        for (int i = 0; i < CHOICES.length; i++) {
            final String action = CHOICES[i][0];
            Button b = new Button(this);
            b.setAllCaps(false);
            b.setText(label(i, false));
            b.setTextColor(Color.WHITE);
            b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 21);
            b.setBackground(tileBackground(i == CHOICES.length - 1));
            b.setPadding(dp(16), dp(24), dp(16), dp(24));
            b.setOnClickListener(new View.OnClickListener() {
                public void onClick(View v) { run(action); }
            });
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, dp(150), 1f);
            lp.setMargins(dp(10), 0, dp(10), 0);
            row.addView(b, lp);
            buttons[i] = b;
        }

        status = text("Checking receivers…", 18, Color.rgb(160, 170, 185));
        LinearLayout.LayoutParams stLp = new LinearLayout.LayoutParams(-2, -2);
        stLp.topMargin = dp(28);
        root.addView(status, stLp);
        setContentView(root);
        buttons[0].requestFocus();
        request("status", false);
    }

    void run(String action) {
        for (Button b : buttons) b.setEnabled(false);
        status.setTextColor(Color.rgb(160, 170, 185));
        status.setText("stop".equals(action) ? "Stopping…" : "Starting…");
        request(action, true);
    }

    void request(final String action, final boolean closeAfter) {
        new Thread(new Runnable() {
            public void run() {
                String json = null, error = null;
                try {
                    HttpURLConnection http = (HttpURLConnection) new URL(
                            "http://127.0.0.1:8787/cgi-bin/cast.cgi?action=" + action).openConnection();
                    http.setConnectTimeout(3000);
                    http.setReadTimeout(15000);
                    InputStream in = http.getInputStream();
                    StringBuilder body = new StringBuilder();
                    byte[] buf = new byte[1024];
                    for (int n; (n = in.read(buf)) > 0; ) body.append(new String(buf, 0, n, "UTF-8"));
                    in.close();
                    json = body.toString();
                } catch (Exception e) {
                    error = e.getMessage();
                }
                final String reply = json, failure = error;
                main.post(new Runnable() {
                    public void run() { show(action, reply, failure, closeAfter); }
                });
            }
        }).start();
    }

    void show(String action, String json, String error, boolean closeAfter) {
        for (int i = 0; i < CHOICES.length; i++) {
            buttons[i].setEnabled(true);
            if (CHOICES[i][0].equals(action)) buttons[i].requestFocus();
        }
        if (json == null) {
            status.setTextColor(Color.rgb(248, 113, 113));
            status.setText("Casting control failed: " + error);
            return;
        }
        for (int i = 0; i < CHOICES.length - 1; i++) {
            int running = json.indexOf("\"running\"");
            boolean on = running >= 0 && json.indexOf("\"" + CHOICES[i][0] + "\":true", running) >= 0;
            buttons[i].setText(label(i, on));
        }
        boolean ok = json.contains("\"status\":\"ok\"");
        status.setTextColor(ok ? Color.rgb(52, 211, 153) : Color.rgb(248, 113, 113));
        status.setText(field(json, "detail"));
        if (ok && closeAfter) {
            main.postDelayed(new Runnable() { public void run() { finish(); } }, 2500);
        }
    }

    CharSequence label(int i, boolean running) {
        String head = (running ? "● " : "") + CHOICES[i][1];
        SpannableString s = new SpannableString(head + "\n" + CHOICES[i][2]);
        s.setSpan(new RelativeSizeSpan(0.72f), head.length(), s.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        s.setSpan(new ForegroundColorSpan(Color.rgb(185, 195, 208)), head.length(), s.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        return s;
    }

    static String field(String json, String key) {
        int start = json.indexOf("\"" + key + "\":\"");
        if (start < 0) return "";
        start += key.length() + 4;
        int end = json.indexOf('"', start);
        return end > start ? json.substring(start, end) : "";
    }

    StateListDrawable tileBackground(boolean danger) {
        StateListDrawable states = new StateListDrawable();
        states.addState(new int[]{android.R.attr.state_focused}, shape(danger ? "#7F1D1D" : "#065F46", danger ? "#F87171" : "#34D399"));
        states.addState(new int[]{}, shape("#1A1F27", "#2C3542"));
        return states;
    }

    GradientDrawable shape(String fill, String stroke) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(Color.parseColor(fill));
        g.setStroke(dp(3), Color.parseColor(stroke));
        g.setCornerRadius(dp(16));
        return g;
    }

    TextView text(String s, int sp, int color) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        t.setTextColor(color);
        t.setGravity(Gravity.CENTER);
        return t;
    }

    int dp(int v) { return Math.round(v * getResources().getDisplayMetrics().density); }
}
