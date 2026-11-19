"""Bounded manual plot geometry without constrained-layout/GridSpec solving."""


def repair_plot_geometry(panel):
    figure = panel.figure
    figure.set_layout_engine('none')
    width, height = figure.get_size_inches() * figure.dpi
    width, height = max(float(width), 1.0), max(float(height), 1.0)
    left_px, bottom_px, top_px = 70.0, 55.0, 38.0
    if hasattr(panel, 'colourbar'):
        right_px, gap_px, bar_px = 105.0, 16.0, 15.0
        available_w = max(160.0, width - left_px - right_px)
        available_h = max(160.0, height - bottom_px - top_px)
        x0, x1 = panel.axes.get_xlim()
        y0, y1 = panel.axes.get_ylim()
        data_ratio = abs((x1 - x0) / (y1 - y0)) if y1 != y0 else 1.0
        # Preserve data proportions when practical, but never create a ribbon-like
        # map. The visible axes box stays between 3:4 and 4:3.
        box_ratio = min(max(data_ratio, 0.75), 4.0 / 3.0)
        axes_w = min(available_w, available_h * box_ratio)
        axes_h = min(available_h, available_w / box_ratio)
        left = left_px + max(0.0, (available_w - axes_w) / 2.0)
        bottom = bottom_px + max(0.0, (available_h - axes_h) / 2.0)
        panel.axes.set_aspect('auto')
        panel.colourbar.ax.set_axes_locator(None)
        # Disable Colorbar's internal fixed box-aspect so the rendered bar uses
        # exactly the same bottom and height as the map axes.
        panel.colourbar.ax.set_box_aspect(None)
        panel.colourbar.ax.set_aspect('auto')
        panel.axes.set_position([left / width, bottom / height,
                                 axes_w / width, axes_h / height])
        panel.colourbar.ax.set_position([(left + axes_w + gap_px) / width,
                                        bottom / height, bar_px / width,
                                        axes_h / height])
    else:
        right_px = 28.0
        panel.ax.set_position([left_px / width, bottom_px / height,
                               max(0.2, (width-left_px-right_px)/width),
                               max(0.2, (height-bottom_px-top_px)/height)])
