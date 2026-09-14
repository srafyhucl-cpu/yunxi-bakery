const BEIJING_ADDRESS_PREFIX_PATTERN =
  /^(?:北京市?)?(?:东城区|西城区|朝阳区|丰台区|石景山区|海淀区|门头沟区|房山区|通州区|顺义区|昌平区|大兴区|怀柔区|平谷区|密云区|延庆区)?/;
const ADDRESS_SEPARATOR_PATTERN = /[\s,，、;；-]+/g;

export function normalizeAddressText(value: string): string {
  return value.trim().replace(ADDRESS_SEPARATOR_PATTERN, "");
}

export function getAddressDetailText(value: string): string {
  return normalizeAddressText(value).replace(BEIJING_ADDRESS_PREFIX_PATTERN, "");
}

export function isAddressDetailedEnough(value: string): boolean {
  return getAddressDetailText(value).length >= 4;
}
