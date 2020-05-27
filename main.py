from scripts.experiments_helper import trainer_protocol, get_configs


def main(cfg):
    worker = trainer_protocol[cfg.exp_prefix](cfg)
    worker.run()

    ## wait to be implemented
    #worker = tester_protocol[cfg.exp_prefix](cfg)
    #worker.run()


if __name__ == "__main__":
    config, _ = get_configs()
    main(config)