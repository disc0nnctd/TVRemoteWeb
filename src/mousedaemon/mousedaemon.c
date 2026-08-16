/* mousedaemon — tiny WebSocket-to-evdev mouse bridge for Android TV.
 *
 * Part of TVRemoteWeb (https://github.com/disc0nnctd/TVRemoteWeb).
 *
 * Listens on 0.0.0.0:8788 and accepts one WebSocket text-frame stream at a
 * time. Commands:
 *
 *   T <token>   authenticate (required first if TVR_TOKEN is set)
 *   M <dx> <dy> relative pointer motion
 *   CL CR CM    click left / right / middle
 *   DL DR DM    button down
 *   UL UR UM    button up
 *   W <n>       wheel, n clicks (negative = down)
 *
 * Pointer output device, in order of preference:
 *   1. $TVR_EVDEV if set
 *   2. auto-detected /dev/input/event* advertising REL_X + REL_Y + BTN_LEFT
 *      and NOT advertising EV_ABS (skips touchscreens/digitisers)
 *   3. a virtual mouse created through /dev/uinput
 *
 * Step 2 is what makes this portable: on the Allwinner H713 the IR receiver
 * (sunxi-ir-uinput) already exposes a relative pointer, so writing to it gives
 * a real system cursor with no extra device. Boxes without such a node fall
 * through to step 3.
 *
 * Build (static, no libc dependency at runtime):
 *   arm-linux-gnueabihf-gcc -static -O2 -o mousedaemon-armv7 mousedaemon.c
 *   aarch64-linux-gnu-gcc   -static -O2 -o mousedaemon-arm64 mousedaemon.c
 *
 * Environment:
 *   TVR_WS_PORT  listen port           (default 8788)
 *   TVR_TOKEN    required auth token   (default: no auth)
 *   TVR_EVDEV    force a specific node (default: auto-detect)
 * The legacy BEEM_* names are still honoured.
 *
 * SPDX-License-Identifier: MIT
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <signal.h>
#include <dirent.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <sys/time.h>
#include <linux/input.h>
#include <linux/input-event-codes.h>
#include <linux/uinput.h>

/* Minimal SHA-1 for the WebSocket handshake (public-domain implementation) */
typedef struct { unsigned int state[5]; unsigned int count[2]; unsigned char buffer[64]; } SHA1_CTX;
#define ROL(v,b) (((v)<<(b))|((v)>>(32-(b))))
#define BLK0(i) (block->l[i] = (ROL(block->l[i],24)&0xFF00FF00)|(ROL(block->l[i],8)&0x00FF00FF))
#define BLK(i) (block->l[i&15] = ROL(block->l[(i+13)&15]^block->l[(i+8)&15]^block->l[(i+2)&15]^block->l[i&15],1))
#define R0(v,w,x,y,z,i) z+=((w&(x^y))^y)+BLK0(i)+0x5A827999+ROL(v,5);w=ROL(w,30);
#define R1(v,w,x,y,z,i) z+=((w&(x^y))^y)+BLK(i)+0x5A827999+ROL(v,5);w=ROL(w,30);
#define R2(v,w,x,y,z,i) z+=(w^x^y)+BLK(i)+0x6ED9EBA1+ROL(v,5);w=ROL(w,30);
#define R3(v,w,x,y,z,i) z+=(((w|x)&y)|(w&x))+BLK(i)+0x8F1BBCDC+ROL(v,5);w=ROL(w,30);
#define R4(v,w,x,y,z,i) z+=(w^x^y)+BLK(i)+0xCA62C1D6+ROL(v,5);w=ROL(w,30);
static void sha1_transform(unsigned int state[5], const unsigned char b[64]) {
    unsigned int a,c,d,e,i; typedef union { unsigned char c[64]; unsigned int l[16]; } CB; CB workspace; CB* block=&workspace;
    memcpy(block, b, 64); a=state[0]; c=state[1]; d=state[2]; e=state[3]; unsigned int f=state[4];
    R0(a,c,d,e,f, 0); R0(f,a,c,d,e, 1); R0(e,f,a,c,d, 2); R0(d,e,f,a,c, 3); R0(c,d,e,f,a, 4);
    R0(a,c,d,e,f, 5); R0(f,a,c,d,e, 6); R0(e,f,a,c,d, 7); R0(d,e,f,a,c, 8); R0(c,d,e,f,a, 9);
    R0(a,c,d,e,f,10); R0(f,a,c,d,e,11); R0(e,f,a,c,d,12); R0(d,e,f,a,c,13); R0(c,d,e,f,a,14); R0(a,c,d,e,f,15);
    R1(f,a,c,d,e,16); R1(e,f,a,c,d,17); R1(d,e,f,a,c,18); R1(c,d,e,f,a,19);
    R2(a,c,d,e,f,20); R2(f,a,c,d,e,21); R2(e,f,a,c,d,22); R2(d,e,f,a,c,23); R2(c,d,e,f,a,24);
    R2(a,c,d,e,f,25); R2(f,a,c,d,e,26); R2(e,f,a,c,d,27); R2(d,e,f,a,c,28); R2(c,d,e,f,a,29);
    R2(a,c,d,e,f,30); R2(f,a,c,d,e,31); R2(e,f,a,c,d,32); R2(d,e,f,a,c,33); R2(c,d,e,f,a,34);
    R2(a,c,d,e,f,35); R2(f,a,c,d,e,36); R2(e,f,a,c,d,37); R2(d,e,f,a,c,38); R2(c,d,e,f,a,39);
    R3(a,c,d,e,f,40); R3(f,a,c,d,e,41); R3(e,f,a,c,d,42); R3(d,e,f,a,c,43); R3(c,d,e,f,a,44);
    R3(a,c,d,e,f,45); R3(f,a,c,d,e,46); R3(e,f,a,c,d,47); R3(d,e,f,a,c,48); R3(c,d,e,f,a,49);
    R3(a,c,d,e,f,50); R3(f,a,c,d,e,51); R3(e,f,a,c,d,52); R3(d,e,f,a,c,53); R3(c,d,e,f,a,54);
    R3(a,c,d,e,f,55); R3(f,a,c,d,e,56); R3(e,f,a,c,d,57); R3(d,e,f,a,c,58); R3(c,d,e,f,a,59);
    R4(a,c,d,e,f,60); R4(f,a,c,d,e,61); R4(e,f,a,c,d,62); R4(d,e,f,a,c,63); R4(c,d,e,f,a,64);
    R4(a,c,d,e,f,65); R4(f,a,c,d,e,66); R4(e,f,a,c,d,67); R4(d,e,f,a,c,68); R4(c,d,e,f,a,69);
    R4(a,c,d,e,f,70); R4(f,a,c,d,e,71); R4(e,f,a,c,d,72); R4(d,e,f,a,c,73); R4(c,d,e,f,a,74);
    R4(a,c,d,e,f,75); R4(f,a,c,d,e,76); R4(e,f,a,c,d,77); R4(d,e,f,a,c,78); R4(c,d,e,f,a,79);
    state[0]+=a; state[1]+=c; state[2]+=d; state[3]+=e; state[4]+=f; (void)i;
}
static void sha1_init(SHA1_CTX* c){c->state[0]=0x67452301;c->state[1]=0xEFCDAB89;c->state[2]=0x98BADCFE;c->state[3]=0x10325476;c->state[4]=0xC3D2E1F0;c->count[0]=c->count[1]=0;}
static void sha1_update(SHA1_CTX* c, const unsigned char* d, unsigned int len){
    unsigned int i,j=c->count[0]; if((c->count[0]+=len<<3)<j) c->count[1]++; c->count[1]+=(len>>29); j=(j>>3)&63;
    if((j+len)>63){memcpy(&c->buffer[j],d,(i=64-j)); sha1_transform(c->state,c->buffer); for(;i+63<len;i+=64) sha1_transform(c->state,&d[i]); j=0;} else i=0;
    memcpy(&c->buffer[j],&d[i],len-i);
}
static void sha1_final(unsigned char digest[20], SHA1_CTX* c){
    unsigned int i; unsigned char fc[8]; for(i=0;i<8;i++) fc[i]=(unsigned char)((c->count[(i>=4?0:1)]>>((3-(i&3))*8))&0xff);
    unsigned char n=0x80; sha1_update(c,&n,1); while((c->count[0]&504)!=448){n=0; sha1_update(c,&n,1);}
    sha1_update(c,fc,8); for(i=0;i<20;i++) digest[i]=(unsigned char)((c->state[i>>2]>>((3-(i&3))*8))&0xff);
}

static const char b64tab[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
static void b64encode(const unsigned char* in, int inlen, char* out){
    int i,j=0; for(i=0;i<inlen-2;i+=3){
        out[j++]=b64tab[(in[i]>>2)&0x3F];
        out[j++]=b64tab[((in[i]&0x3)<<4)|((in[i+1]&0xF0)>>4)];
        out[j++]=b64tab[((in[i+1]&0xF)<<2)|((in[i+2]&0xC0)>>6)];
        out[j++]=b64tab[in[i+2]&0x3F];
    }
    if(i<inlen){
        out[j++]=b64tab[(in[i]>>2)&0x3F];
        if(i==inlen-1){out[j++]=b64tab[(in[i]&0x3)<<4]; out[j++]='='; out[j++]='=';}
        else{out[j++]=b64tab[((in[i]&0x3)<<4)|((in[i+1]&0xF0)>>4)]; out[j++]=b64tab[(in[i+1]&0xF)<<2]; out[j++]='=';}
    }
    out[j]='\0';
}

/* ------------------------------------------------------------------ */
/* pointer device                                                      */
/* ------------------------------------------------------------------ */
static int ev_fd = -1;
static int owns_uinput = 0;   /* set when we created the device ourselves */

static int bit_set(const unsigned char* bits, int n){ return (bits[n/8] >> (n%8)) & 1; }

/* Return an open fd if `path` is a usable relative pointer, else -1. */
static int probe_evdev(const char* path){
    int fd = open(path, O_RDWR | O_NONBLOCK);
    if (fd < 0) return -1;

    unsigned char evbits[(EV_MAX+7)/8];
    unsigned char relbits[(REL_MAX+7)/8];
    unsigned char keybits[(KEY_MAX+7)/8];
    memset(evbits, 0, sizeof evbits);
    memset(relbits, 0, sizeof relbits);
    memset(keybits, 0, sizeof keybits);

    if (ioctl(fd, EVIOCGBIT(0, sizeof evbits), evbits) < 0) { close(fd); return -1; }
    /* Skip absolute pointers: touchscreens and digitisers would fight us. */
    if (bit_set(evbits, EV_ABS)) { close(fd); return -1; }
    if (!bit_set(evbits, EV_REL) || !bit_set(evbits, EV_KEY)) { close(fd); return -1; }

    ioctl(fd, EVIOCGBIT(EV_REL, sizeof relbits), relbits);
    ioctl(fd, EVIOCGBIT(EV_KEY, sizeof keybits), keybits);

    if (bit_set(relbits, REL_X) && bit_set(relbits, REL_Y) && bit_set(keybits, BTN_LEFT))
        return fd;

    close(fd);
    return -1;
}

/* Scan /dev/input for a relative pointer. Fills `chosen` with the path. */
static int find_evdev(char* chosen, size_t chosen_len){
    DIR* d = opendir("/dev/input");
    if (!d) return -1;
    struct dirent* e;
    int best = -1;
    char path[300];
    while ((e = readdir(d)) != NULL) {
        if (strncmp(e->d_name, "event", 5) != 0) continue;
        snprintf(path, sizeof path, "/dev/input/%s", e->d_name);
        int fd = probe_evdev(path);
        if (fd >= 0) {
            best = fd;
            snprintf(chosen, chosen_len, "%s", path);
            char name[256] = {0};
            if (ioctl(fd, EVIOCGNAME(sizeof name - 1), name) >= 0 && name[0])
                fprintf(stderr, "mousedaemon: using %s (%s)\n", path, name);
            else
                fprintf(stderr, "mousedaemon: using %s\n", path);
            break;
        }
    }
    closedir(d);
    return best;
}

/* Last resort: create our own virtual mouse. */
static int create_uinput(void){
    int fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
    if (fd < 0) {
        fprintf(stderr, "mousedaemon: open /dev/uinput: %s\n", strerror(errno));
        return -1;
    }
    ioctl(fd, UI_SET_EVBIT, EV_KEY);
    ioctl(fd, UI_SET_KEYBIT, BTN_LEFT);
    ioctl(fd, UI_SET_KEYBIT, BTN_RIGHT);
    ioctl(fd, UI_SET_KEYBIT, BTN_MIDDLE);
    ioctl(fd, UI_SET_EVBIT, EV_REL);
    ioctl(fd, UI_SET_RELBIT, REL_X);
    ioctl(fd, UI_SET_RELBIT, REL_Y);
    ioctl(fd, UI_SET_RELBIT, REL_WHEEL);
    ioctl(fd, UI_SET_RELBIT, REL_HWHEEL);
    ioctl(fd, UI_SET_EVBIT, EV_SYN);

    struct uinput_user_dev dev;
    memset(&dev, 0, sizeof dev);
    snprintf(dev.name, UINPUT_MAX_NAME_SIZE, "tvremoteweb-mouse");
    dev.id.bustype = BUS_VIRTUAL;
    dev.id.vendor  = 0x1209;
    dev.id.product = 0x7772;
    dev.id.version = 1;

    if (write(fd, &dev, sizeof dev) != (ssize_t)sizeof dev) {
        fprintf(stderr, "mousedaemon: uinput setup write failed: %s\n", strerror(errno));
        close(fd); return -1;
    }
    if (ioctl(fd, UI_DEV_CREATE) < 0) {
        fprintf(stderr, "mousedaemon: UI_DEV_CREATE: %s\n", strerror(errno));
        close(fd); return -1;
    }
    /* Give Android's InputReader a moment to enumerate the new device. */
    usleep(300 * 1000);
    fprintf(stderr, "mousedaemon: created virtual mouse via /dev/uinput\n");
    owns_uinput = 1;
    return fd;
}

static void send_event(unsigned short type, unsigned short code, int value){
    struct input_event ev;
    memset(&ev, 0, sizeof(ev));
    /* leave the timestamp zeroed; Android's InputReader stamps on arrival */
    ev.type = type; ev.code = code; ev.value = value;
    if (write(ev_fd, &ev, sizeof(ev)) < 0) perror("mousedaemon: write");
}
static void mouse_move(int dx, int dy){
    if (dx) send_event(EV_REL, REL_X, dx);
    if (dy) send_event(EV_REL, REL_Y, dy);
    if (dx || dy) send_event(EV_SYN, SYN_REPORT, 0);
}
static void mouse_button(int code, int down){
    send_event(EV_KEY, code, down);
    send_event(EV_SYN, SYN_REPORT, 0);
}
static void mouse_wheel(int n){
    send_event(EV_REL, REL_WHEEL, n);
    send_event(EV_SYN, SYN_REPORT, 0);
}
static int parse_btn(const char* s){
    if (!s || !*s) return BTN_LEFT;
    switch (s[0]) { case 'R': case 'r': return BTN_RIGHT; case 'M': case 'm': return BTN_MIDDLE; default: return BTN_LEFT; }
}

/* ------------------------------------------------------------------ */
/* WebSocket                                                           */
/* ------------------------------------------------------------------ */
static int read_line(int fd, char* buf, int max){
    int n=0; char c;
    while (n < max-1) {
        int r = read(fd, &c, 1); if (r <= 0) return -1;
        buf[n++] = c;
        if (n >= 2 && buf[n-2] == '\r' && buf[n-1] == '\n') { buf[n] = 0; return n; }
    }
    return -1;
}
static int ws_handshake(int cfd){
    char line[1024], key[256] = {0};
    if (read_line(cfd, line, sizeof(line)) < 0) return -1;   /* request line */
    for (;;) {
        if (read_line(cfd, line, sizeof(line)) < 0) return -1;
        if (line[0] == '\r' && line[1] == '\n') break;
        if (strncasecmp(line, "sec-websocket-key:", 18) == 0) {
            char* p = line + 18; while (*p == ' ') p++;
            int i = 0; while (*p && *p != '\r' && i < 250) key[i++] = *p++;
            key[i] = 0;
        }
    }
    if (!key[0]) return -1;
    char concat[512]; snprintf(concat, sizeof(concat), "%s258EAFA5-E914-47DA-95CA-C5AB0DC85B11", key);
    SHA1_CTX ctx; sha1_init(&ctx);
    sha1_update(&ctx, (unsigned char*)concat, strlen(concat));
    unsigned char digest[20]; sha1_final(digest, &ctx);
    char accept[64]; b64encode(digest, 20, accept);
    char resp[512]; int rn = snprintf(resp, sizeof(resp),
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Accept: %s\r\n\r\n", accept);
    if (write(cfd, resp, rn) != rn) return -1;
    return 0;
}
/* Read one text frame into buf. Returns length, 0 for ignorable, -1 to close. */
static int ws_recv(int cfd, char* buf, int max){
    unsigned char hdr[2];
    if (read(cfd, hdr, 2) != 2) return -1;
    int op = hdr[0] & 0x0F, masked = hdr[1] & 0x80;
    unsigned long long len = hdr[1] & 0x7F;
    if (op == 0x8) return -1;                       /* close */
    if (op == 0x9) { unsigned char pong[2] = {0x8A, 0x00}; if (write(cfd, pong, 2) != 2) return -1; return 0; }
    if (op != 0x1 && op != 0x0) return 0;           /* skip binary/continuation */
    if (len == 126) { unsigned char e[2]; if (read(cfd, e, 2) != 2) return -1; len = (e[0]<<8)|e[1]; }
    else if (len == 127) { unsigned char e[8]; if (read(cfd, e, 8) != 8) return -1; len = 0; for (int i=0;i<8;i++) len = (len<<8)|e[i]; }
    if (len >= (unsigned long long)max) return -1;
    unsigned char mask[4] = {0};
    if (masked) { if (read(cfd, mask, 4) != 4) return -1; }
    int got = 0;
    while (got < (int)len) {
        int r = read(cfd, buf + got, (int)len - got);
        if (r <= 0) return -1;
        got += r;
    }
    if (masked) { for (int i = 0; i < (int)len; i++) buf[i] ^= mask[i & 3]; }
    buf[len] = 0;
    return (int)len;
}

static const char* expected_token = NULL;
static int authed = 0;
static void handle_cmd(char* s){
    if (!s || !*s) return;
    char* end = s + strlen(s);
    while (end > s && (*(end-1) == '\n' || *(end-1) == '\r' || *(end-1) == ' ')) end--;
    *end = 0;
    if (!authed) {
        if (s[0] == 'T' && s[1] == ' ') {
            if (!expected_token || strcmp(s + 2, expected_token) == 0) authed = 1;
        }
        return;                                     /* drop everything until authed */
    }
    if (s[0] == 'M' && s[1] == ' ') {
        int dx = 0, dy = 0;
        if (sscanf(s + 2, "%d %d", &dx, &dy) == 2) mouse_move(dx, dy);
    } else if (s[0] == 'C' && s[1]) {
        int btn = parse_btn(s + 1);
        mouse_button(btn, 1); mouse_button(btn, 0);
    } else if (s[0] == 'D' && s[1]) {
        mouse_button(parse_btn(s + 1), 1);
    } else if (s[0] == 'U' && s[1]) {
        mouse_button(parse_btn(s + 1), 0);
    } else if (s[0] == 'W' && s[1] == ' ') {
        mouse_wheel(atoi(s + 2));
    }
}

static const char* env2(const char* a, const char* b){
    const char* v = getenv(a);
    if (!v || !*v) v = getenv(b);
    if (v && !*v) v = NULL;
    return v;
}

int main(void){
    signal(SIGPIPE, SIG_IGN);

    const char* forced = env2("TVR_EVDEV", "BEEM_EVDEV");
    const char* pstr   = env2("TVR_WS_PORT", "BEEM_WS_PORT");
    expected_token     = env2("TVR_TOKEN", "BEEM_TOKEN");
    int port = pstr ? atoi(pstr) : 8788;
    if (port <= 0 || port > 65535) port = 8788;

    char chosen[300] = {0};
    if (forced) {
        ev_fd = open(forced, O_RDWR | O_NONBLOCK);
        if (ev_fd < 0) ev_fd = open(forced, O_WRONLY | O_NONBLOCK);
        if (ev_fd < 0) { fprintf(stderr, "mousedaemon: open %s: %s\n", forced, strerror(errno)); return 1; }
        snprintf(chosen, sizeof chosen, "%s", forced);
        fprintf(stderr, "mousedaemon: using %s (forced)\n", chosen);
    } else {
        ev_fd = find_evdev(chosen, sizeof chosen);
        if (ev_fd < 0) {
            fprintf(stderr, "mousedaemon: no relative pointer found, falling back to uinput\n");
            ev_fd = create_uinput();
            snprintf(chosen, sizeof chosen, "uinput:tvremoteweb-mouse");
        }
        if (ev_fd < 0) { fprintf(stderr, "mousedaemon: no usable pointer device\n"); return 1; }
    }

    int lfd = socket(AF_INET, SOCK_STREAM, 0);
    int one = 1; setsockopt(lfd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof addr);
    addr.sin_family = AF_INET; addr.sin_addr.s_addr = htonl(INADDR_ANY); addr.sin_port = htons(port);
    if (bind(lfd, (struct sockaddr*)&addr, sizeof(addr)) < 0) { perror("mousedaemon: bind"); return 1; }
    if (listen(lfd, 4) < 0) { perror("mousedaemon: listen"); return 1; }
    fprintf(stderr, "mousedaemon: listening on ws://0.0.0.0:%d via %s%s\n",
            port, chosen, expected_token ? " (token required)" : " (NO AUTH)");

    for (;;) {
        int cfd = accept(lfd, NULL, NULL);
        if (cfd < 0) { if (errno == EINTR) continue; perror("mousedaemon: accept"); break; }
        int nd = 1; setsockopt(cfd, IPPROTO_TCP, 1, &nd, sizeof(nd)); /* TCP_NODELAY */
        if (ws_handshake(cfd) == 0) {
            authed = expected_token ? 0 : 1;
            char buf[8192];
            for (;;) {
                int r = ws_recv(cfd, buf, sizeof(buf));
                if (r < 0) break;
                if (r > 0) handle_cmd(buf);
            }
        }
        close(cfd);
        authed = 0;
    }
    close(lfd);
    if (owns_uinput) ioctl(ev_fd, UI_DEV_DESTROY);
    close(ev_fd);
    return 0;
}
