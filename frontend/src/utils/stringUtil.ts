const getRandomId = (): string => {
  // 生成10位随机id，只能是字母和数字
  return Math.random().toString(36).substring(2, 12);
};

export { getRandomId };
