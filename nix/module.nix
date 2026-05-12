{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.services.hass-companion;
  defaultPackage = pkgs.callPackage ./package.nix { };
in
{
  options.services.hass-companion = {
    enable = lib.mkEnableOption "Hass Companion MQTT service";

    package = lib.mkOption {
      type = lib.types.package;
      default = defaultPackage;
      description = "The hass-companion package to use.";
    };

    configFile = lib.mkOption {
      type = lib.types.path;
      description = "Path to the hass-companion config.yaml file.";
    };

    environmentFile = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      description = "Path to environment file with MQTT credentials (e.g., .env or sops-nix secret).";
    };

    logLevel = lib.mkOption {
      type = lib.types.enum [
        "DEBUG"
        "INFO"
        "WARNING"
        "ERROR"
      ];
      default = "INFO";
      description = "Logging verbosity level.";
    };

    watchConfig = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Watch config file for changes and reload automatically.";
    };
  };

  config = lib.mkIf cfg.enable {
    systemd.services.hass-companion = {
      description = "Hass Companion — Home Assistant MQTT Companion";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      wantedBy = [ "multi-user.target" ];

      serviceConfig =
        {
          Type = "simple";
          ExecStart = lib.concatStringsSep " " (
            [
              "${cfg.package}/bin/hass-companion"
              "--config"
              (toString cfg.configFile)
              "--log-level"
              cfg.logLevel
            ]
            ++ lib.optionals cfg.watchConfig [ "--watch-config" ]
          );
          Restart = "on-failure";
          RestartSec = 10;
        }
        // lib.optionalAttrs (cfg.environmentFile != null) {
          EnvironmentFile = cfg.environmentFile;
        };
    };
  };
}
