.class public Lcom/tvremote/PqCli;
.super Ljava/lang/Object;
.source "PqCli.java"

# Minimal command bridge to the Allwinner PQ client shipped in HtcSettingsBlue.
# Runtime classpath must include that system APK.

.method private static printValue(Lcom/softwinner/a;I)V
    .locals 2

    sget-object v0, Ljava/lang/System;->out:Ljava/io/PrintStream;
    invoke-virtual {v0, p1}, Ljava/io/PrintStream;->print(I)V
    const-string v1, "="
    invoke-virtual {v0, v1}, Ljava/io/PrintStream;->print(Ljava/lang/String;)V
    invoke-virtual {p0, p1}, Lcom/softwinner/a;->a(I)I
    move-result v1
    invoke-virtual {v0, v1}, Ljava/io/PrintStream;->println(I)V
    return-void
.end method

.method public static main([Ljava/lang/String;)V
    .locals 5

    array-length v0, p0
    const/4 v1, 0x1
    if-lt v0, v1, :usage

    new-instance v0, Lcom/softwinner/a;
    invoke-direct {v0}, Lcom/softwinner/a;-><init>()V

    const/4 v1, 0x0
    aget-object v1, p0, v1
    const-string v2, "status"
    invoke-virtual {v2, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v2
    if-eqz v2, :not_status

    const/4 v2, 0x1
    invoke-static {v0, v2}, Lcom/tvremote/PqCli;->printValue(Lcom/softwinner/a;I)V
    const/4 v2, 0x2
    invoke-static {v0, v2}, Lcom/tvremote/PqCli;->printValue(Lcom/softwinner/a;I)V
    const/4 v2, 0x3
    invoke-static {v0, v2}, Lcom/tvremote/PqCli;->printValue(Lcom/softwinner/a;I)V
    const/4 v2, 0x4
    invoke-static {v0, v2}, Lcom/tvremote/PqCli;->printValue(Lcom/softwinner/a;I)V
    const/4 v2, 0x5
    invoke-static {v0, v2}, Lcom/tvremote/PqCli;->printValue(Lcom/softwinner/a;I)V
    const/4 v2, 0x6
    invoke-static {v0, v2}, Lcom/tvremote/PqCli;->printValue(Lcom/softwinner/a;I)V
    const/4 v2, 0x7
    invoke-static {v0, v2}, Lcom/tvremote/PqCli;->printValue(Lcom/softwinner/a;I)V
    const/16 v2, 0x8
    invoke-static {v0, v2}, Lcom/tvremote/PqCli;->printValue(Lcom/softwinner/a;I)V
    const/16 v2, 0x9
    invoke-static {v0, v2}, Lcom/tvremote/PqCli;->printValue(Lcom/softwinner/a;I)V
    const/16 v2, 0xa
    invoke-static {v0, v2}, Lcom/tvremote/PqCli;->printValue(Lcom/softwinner/a;I)V
    const/16 v2, 0xb
    invoke-static {v0, v2}, Lcom/tvremote/PqCli;->printValue(Lcom/softwinner/a;I)V
    const/16 v2, 0xc
    invoke-static {v0, v2}, Lcom/tvremote/PqCli;->printValue(Lcom/softwinner/a;I)V
    const/16 v2, 0xd
    invoke-static {v0, v2}, Lcom/tvremote/PqCli;->printValue(Lcom/softwinner/a;I)V
    return-void

    :not_status
    array-length v2, p0
    const/4 v3, 0x2
    if-lt v2, v3, :usage
    const/4 v2, 0x1
    aget-object v2, p0, v2
    invoke-static {v2}, Ljava/lang/Integer;->parseInt(Ljava/lang/String;)I
    move-result v2

    const-string v3, "get"
    invoke-virtual {v3, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v3
    if-eqz v3, :maybe_set
    invoke-virtual {v0, v2}, Lcom/softwinner/a;->a(I)I
    move-result v0
    sget-object v1, Ljava/lang/System;->out:Ljava/io/PrintStream;
    invoke-virtual {v1, v0}, Ljava/io/PrintStream;->println(I)V
    return-void

    :maybe_set
    const-string v3, "set"
    invoke-virtual {v3, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v1
    if-eqz v1, :usage
    array-length v1, p0
    const/4 v3, 0x3
    if-lt v1, v3, :usage
    const/4 v1, 0x2
    aget-object v1, p0, v1
    invoke-static {v1}, Ljava/lang/Integer;->parseInt(Ljava/lang/String;)I
    move-result v1
    invoke-virtual {v0, v2, v1}, Lcom/softwinner/a;->e(II)I
    move-result v0
    sget-object v1, Ljava/lang/System;->out:Ljava/io/PrintStream;
    invoke-virtual {v1, v0}, Ljava/io/PrintStream;->println(I)V
    return-void

    :usage
    sget-object v0, Ljava/lang/System;->err:Ljava/io/PrintStream;
    const-string v1, "usage: PqCli status | get CHANNEL | set CHANNEL VALUE"
    invoke-virtual {v0, v1}, Ljava/io/PrintStream;->println(Ljava/lang/String;)V
    return-void
.end method
