export const MAX_TREE_ZOOM = 1.5;
export const MIN_TREE_ZOOM = 0.01;

export function fitTreeZoom(viewportWidth, viewportHeight, contentWidth, contentHeight) {
  const usableWidth = Math.max(1, Number(viewportWidth) - 2);
  const usableHeight = Math.max(1, Number(viewportHeight) - 2);
  const width = Math.max(1, Number(contentWidth));
  const height = Math.max(1, Number(contentHeight));
  const fitted = Math.min(MAX_TREE_ZOOM, usableWidth / width, usableHeight / height);
  return Math.max(MIN_TREE_ZOOM, Math.floor((fitted + Number.EPSILON) * 100) / 100);
}

export function clampTreeZoom(value, fittedZoom) {
  const minimum = Math.min(MAX_TREE_ZOOM, Math.max(MIN_TREE_ZOOM, Number(fittedZoom) || MIN_TREE_ZOOM));
  const rounded = Math.round((Number(value) || minimum) * 100) / 100;
  return Math.min(MAX_TREE_ZOOM, Math.max(minimum, rounded));
}
