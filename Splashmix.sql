CREATE TABLE `conjunto` (
  `id` integer PRIMARY KEY,
  `sitio` varchar(255),
  `nombre` varchar(255),
  `created_at` timestamp
);

CREATE TABLE `producto` (
  `id` integer PRIMARY KEY,
  `nombre` varchar(255),
  `cantidad` int,
  `id_tipo_producto` integer NOT NULL,
  `id_conjunto` integer NOT NULL,
  `precio_base` varchar(255),
  `created_at` timestamp
);

CREATE TABLE `tipo_producto` (
  `id` integer PRIMARY KEY,
  `nombre` varchar(255),
  `unidad_base` varchar(255)
);

CREATE TABLE `pertenencia` (
  `id` integer PRIMARY KEY,
  `id_conjunto` integer NOT NULL,
  `id_producto` integer NOT NULL,
  `created_at` timestamp
);

CREATE TABLE `pais` (
  `id` integer PRIMARY KEY,
  `nombre` varchar(255),
  `moneda` varchar(255),
  `moneda_tic` varchar(255),
  `simbolo` varchar(255),
  `side` bool,
  `decs` int,
  `created_at` timestamp
);

CREATE TABLE `textos` (
  `id` integer PRIMARY KEY,
  `id_tipo_producto` integer NOT NULL,
  `id_pais` integer NOT NULL,
  `unidad` varchar(255),
  `unidades` varchar(255)
);

CREATE TABLE `precio` (
  `id` integer PRIMARY KEY,
  `nombre` varchar(255),
  `id_pertenencia` integer NOT NULL,
  `id_pais` integer NOT NULL,
  `price_id` varchar(255),
  `cantidad_precio` int,
  `ratio_imagen` int,
  `status` varchar(255),
  `created_at` timestamp
);

ALTER TABLE `pertenencia` ADD FOREIGN KEY (`id_conjunto`) REFERENCES `conjunto` (`id`);

ALTER TABLE `pertenencia` ADD FOREIGN KEY (`id_producto`) REFERENCES `producto` (`id`);

ALTER TABLE `precio` ADD FOREIGN KEY (`id_pertenencia`) REFERENCES `pertenencia` (`id`);

ALTER TABLE `precio` ADD FOREIGN KEY (`id_pais`) REFERENCES `pais` (`id`);

ALTER TABLE `textos` ADD FOREIGN KEY (`id_tipo_producto`) REFERENCES `tipo_producto` (`id`);

ALTER TABLE `textos` ADD FOREIGN KEY (`id_pais`) REFERENCES `pais` (`id`);

ALTER TABLE `producto` ADD FOREIGN KEY (`id_tipo_producto`) REFERENCES `tipo_producto` (`id`);
