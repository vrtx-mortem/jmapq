package com.example.ann;

public class NestedAnnotationResource {
    @Outer(@Inner("value"))
    @ArrayAnn({ @Inner("a"), @Inner("b") })
    public void work() {
    }
}
