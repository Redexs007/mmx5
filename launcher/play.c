/* MegaManX5-Play: abre o jogo direto, sem launcher. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <limits.h>
#include <libgen.h>
#include <fcntl.h>
int main(int argc, char **argv) {
    char self[PATH_MAX], base[PATH_MAX], game[PATH_MAX], rt[PATH_MAX], cfg[PATH_MAX], lau[PATH_MAX];
    ssize_t n = readlink("/proc/self/exe", self, sizeof self - 1);
    if (n < 0) { perror("readlink"); return 1; }
    self[n] = 0; strncpy(base, dirname(self), sizeof base - 1); base[sizeof base - 1] = 0;
    const char *g = getenv("MMX5_GAME_DIR");
    if (g && *g) snprintf(game, sizeof game, "%s", g); else snprintf(game, sizeof game, "%s/game", base);
    snprintf(rt, sizeof rt, "%s/mmx5-runtime", game);
    snprintf(cfg, sizeof cfg, "%s/settings.toml", game);
    snprintf(lau, sizeof lau, "%s/MegaManX5-Launcher", base);
    int has_disc = 0;
    FILE *f = fopen(cfg, "r");
    if (f) { char l[4096]; while (fgets(l, sizeof l, f)) if (!strncmp(l, "[disc]", 6)) has_disc = 1; fclose(f); }
    if (access(rt, X_OK) != 0 || !has_disc) {
        fprintf(stderr, "Jogo nao compilado ou disco nao configurado: abrindo o launcher.\n");
        if (access(lau, X_OK) == 0) { execl(lau, lau, (char *)NULL); }
        fprintf(stderr, "Launcher nao encontrado: %s\n", lau); return 1;
    }
    char envp[PATH_MAX]; snprintf(envp, sizeof envp, "%s/launch.env", game);
    FILE *ef = fopen(envp, "r");
    if (ef) { char l[8192]; while (fgets(l, sizeof l, ef)) {
        if (l[0] == '#' || !strchr(l, '=')) continue;
        size_t n2 = strlen(l); while (n2 && (l[n2-1] == '\n' || l[n2-1] == '\r')) l[--n2] = 0;
        char *eq = strchr(l, '='); *eq = 0; setenv(l, eq + 1, 1); }
        fclose(ef); }
    if (chdir(game) != 0) { perror("chdir"); return 1; }
    char **av = calloc(argc + 3, sizeof *av);
    av[0] = rt; av[1] = "--no-launcher";
    for (int i = 1; i < argc; i++) av[i + 1] = argv[i];
    { char lg[PATH_MAX]; snprintf(lg, sizeof lg, "%s/last_run.log", game);
      int fd = open(lg, O_WRONLY | O_CREAT | O_TRUNC, 0644);
      if (fd >= 0) { dup2(fd, 1); dup2(fd, 2); close(fd); } }
    execv(rt, av); perror("execv"); return 1;
}
