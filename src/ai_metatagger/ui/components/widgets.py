import os
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt


class ClickableSlider(QtWidgets.QSlider):

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == QtCore.Qt.LeftButton:
            val = self.pixelPosToRangeValue(event.pos())
            self.setValue(val)
            self.sliderMoved.emit(val)

    def pixelPosToRangeValue(self, pos):
        opt = QtWidgets.QStyleOptionSlider()
        self.initStyleOption(opt)
        gr = self.style().subControlRect(QtWidgets.QStyle.CC_Slider, opt, QtWidgets.QStyle.SC_SliderGroove, self)
        sr = self.style().subControlRect(QtWidgets.QStyle.CC_Slider, opt, QtWidgets.QStyle.SC_SliderHandle, self)

        if self.orientation() == QtCore.Qt.Horizontal:
            sliderLength = sr.width()
            sliderMin = gr.x()
            sliderMax = gr.right() - sliderLength + 1
            pos = pos.x() - sliderLength / 2
        else:
            sliderLength = sr.height()
            sliderMin = gr.y()
            sliderMax = gr.bottom() - sliderLength + 1
            pos = pos.y() - sliderLength / 2

        span = sliderMax - sliderMin
        if span == 0: return self.minimum()

        # calculate value
        val = QtWidgets.QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), int(pos - sliderMin), span, opt.upsideDown)
        return val
