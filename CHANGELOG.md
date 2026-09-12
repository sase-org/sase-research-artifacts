# Changelog

## [0.3.0](https://github.com/sase-org/sase-research-artifacts/compare/v0.2.0...v0.3.0) (2026-09-12)


### ⚠ BREAKING CHANGES

* the `research_a` custom model alias is renamed to `sol_or_grok` and `research_b` is renamed to `opus_or_grok` in this plugin's default_config.yml. Any project or user config referencing the old alias names must be updated to the new names.

### Features

* add opt-in priority input to #research_swarm ([d054715](https://github.com/sase-org/sase-research-artifacts/commit/d054715ded7e2882483155d75b69a260c1154890))
* add optional priority input to #research_swarm ([01a45ed](https://github.com/sase-org/sase-research-artifacts/commit/01a45ed846701df2589b12fe0c2d298891b43018))
* add research suffix input ([68bb0dd](https://github.com/sase-org/sase-research-artifacts/commit/68bb0dd3326adfeaf42637c330b757c6bdece13e))
* **config:** route research swarm image launches through [@image](https://github.com/image) ([93e1f55](https://github.com/sase-org/sase-research-artifacts/commit/93e1f55963b195d80431cb9b10ac935bd3fb81bd))
* remove optional priority input from #research_swarm ([caf12b8](https://github.com/sase-org/sase-research-artifacts/commit/caf12b83968a1cd647c5fcee0b42676d6b263431))
* rename research_a/research_b model aliases to sol_or_grok/opus_or_grok ([e11cdda](https://github.com/sase-org/sase-research-artifacts/commit/e11cddaabbe9c3aeb5e5266750f4998f40a0da0c))
* **research:** use xlarge for swarm lead ([6ed8763](https://github.com/sase-org/sase-research-artifacts/commit/6ed87637a300ea4befb9f994661ac5dda0ba79ef))
* **research:** weight research swarm segments ([526604b](https://github.com/sase-org/sase-research-artifacts/commit/526604b6ea706ccf4668d6aed6aaf7d3a3003eb2))
* **xprompt:** add research swarm runners option ([59a54e0](https://github.com/sase-org/sase-research-artifacts/commit/59a54e0eba0433c94e10c5b688d49363aa27b11b))
* **xprompt:** mention artifact-read derivation in research swarm ([15a4b09](https://github.com/sase-org/sase-research-artifacts/commit/15a4b095489f241459a5700d446cc0b5f996a4fe))
* **xprompts:** hand research reports to the lead via wait.artifacts ([babfb46](https://github.com/sase-org/sase-research-artifacts/commit/babfb46eebf7fe47047ef89034a6456cd8474d8b))
* **xprompts:** instruct research swarm peers to stay independent ([abdaf1f](https://github.com/sase-org/sase-research-artifacts/commit/abdaf1f871ba09c22546a5d68c6509453dabc83b))


### Bug Fixes

* **config:** default research lead to xlarge ([ede2123](https://github.com/sase-org/sase-research-artifacts/commit/ede2123402221754a605ab4b66c2faccb0e29e8f))
* exclude generated research companions from inventory ([46fe923](https://github.com/sase-org/sase-research-artifacts/commit/46fe9235d1043c9efdfbbffc6cff4c9f4278f5eb))
* make research report targets deterministic ([83f4c01](https://github.com/sase-org/sase-research-artifacts/commit/83f4c0154d6f5e50d527582c2377eb36bdcb2ff5))
* **provider:** restrict research highlights producers ([a045047](https://github.com/sase-org/sase-research-artifacts/commit/a045047c76cdd2b762171f8b62a34490839aace8))
* **research:** use queue capacity directive ([5aaa244](https://github.com/sase-org/sase-research-artifacts/commit/5aaa244451eab367eb95d6ce65f03b38e8352407))
* **xprompts:** emit queue priority directive ([cebc7c4](https://github.com/sase-org/sase-research-artifacts/commit/cebc7c4c6a1403f9df7e0bdf40681f1d898b935d))

## [0.2.0](https://github.com/sase-org/sase-research-artifacts/compare/v0.1.0...v0.2.0) (2026-08-18)


### ⚠ BREAKING CHANGES

* The Python distribution is now `sase-research-artifacts` and the import package is now `sase_research_artifacts`; use those names instead of `sase-research` / `sase_research`.

### Features

* Add `wait` argument to #research_swarm ([a7d9e04](https://github.com/sase-org/sase-research-artifacts/commit/a7d9e04999eaca64c753523af529b2be24143afe))
* **provider:** declare research artifact pane metadata ([24daa87](https://github.com/sase-org/sase-research-artifacts/commit/24daa876b135cce8969bbcfc309d15632f2fbaf6))
* **provider:** declare the research ref as a pointer expansion format ([18b23d1](https://github.com/sase-org/sase-research-artifacts/commit/18b23d16fa6772868da81db09adcbc3840b74bce))
* rename research plugin identity ([807e209](https://github.com/sase-org/sase-research-artifacts/commit/807e20989713c97c1d2bc96fb575e88348b9c217))
* **research:** declare ref.icon for the sidecar ref provider spec ([379b362](https://github.com/sase-org/sase-research-artifacts/commit/379b3621a722c213b02fb2f8717d512cdddf3bd3))
* scaffold the sase-research plugin package ([f499469](https://github.com/sase-org/sase-research-artifacts/commit/f499469a39ea5fbf52d3b75a92ac65ae5eba8c37))


### Bug Fixes

* document research swarm wait argument ([189841d](https://github.com/sase-org/sase-research-artifacts/commit/189841d1d4c186ae9b7d82dee4955c7813d56f82))


### Documentation

* mention just test-wheel in the agent build commands ([7be097a](https://github.com/sase-org/sase-research-artifacts/commit/7be097a70a2fda19868116404c7febec185175a2))
* mention the optional wait argument on #research_swarm ([a5a6b1b](https://github.com/sase-org/sase-research-artifacts/commit/a5a6b1b65dbf0c67e8375cc9c15b2a8604122f4d))
* note that the sase 0.17 floor is not on PyPI yet ([46dc0d3](https://github.com/sase-org/sase-research-artifacts/commit/46dc0d34cd119cba58e6a6bd07bae632196d609f))
* state the Python and sase version requirements in the README ([23367af](https://github.com/sase-org/sase-research-artifacts/commit/23367aff1ac6ae588dc290d59886738771e4ad35))

## Changelog
