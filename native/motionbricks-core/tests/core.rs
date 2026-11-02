use motionbricks_core::{Codebook, Error, Matrix, MAX_ELEMENTS};

#[test]
fn linear_layout_and_bias() {
    let x = Matrix::new(2, 2, vec![1., 2., 3., 4.]).unwrap();
    let w = Matrix::new(3, 2, vec![1., 0., 0., 1., 1., 1.]).unwrap();
    assert_eq!(
        x.linear(&w, &[0., 1., 2.]).unwrap().data(),
        &[1., 3., 5., 3., 5., 9.]
    );
    assert!(x.linear(&w, &[0.]).is_err());
}
#[test]
fn stable_softmax() {
    let p = Matrix::new(1, 3, vec![10000., 10000., 10000.])
        .unwrap()
        .softmax()
        .unwrap();
    for x in p.data() {
        assert!((*x - 1. / 3.).abs() < 1e-6);
    }
    let p = Matrix::new(1, 2, vec![-f32::MAX, f32::MAX])
        .unwrap()
        .softmax()
        .unwrap();
    assert_eq!(p.data(), &[0., 1.]);
}
#[test]
fn relu_and_input_validation() {
    assert_eq!(
        Matrix::new(1, 3, vec![-1., 0., 2.])
            .unwrap()
            .relu()
            .unwrap()
            .data(),
        &[0., 0., 2.]
    );
    assert!(matches!(Matrix::new(0, 1, vec![]), Err(Error::Shape)));
    assert!(matches!(Matrix::new(1, 2, vec![0.]), Err(Error::Shape)));
    assert!(matches!(
        Matrix::new(1, 1, vec![f32::NAN]),
        Err(Error::NonFinite)
    ));
    assert!(matches!(
        Matrix::new(usize::MAX, 2, vec![]),
        Err(Error::Limit)
    ));
    assert!(matches!(
        Matrix::new(MAX_ELEMENTS + 1, 1, vec![]),
        Err(Error::Limit)
    ));
}
#[test]
fn overflow_is_error() {
    let x = Matrix::new(1, 1, vec![f32::MAX]).unwrap();
    assert!(matches!(x.linear(&x, &[0.]), Err(Error::NonFinite)));
}
#[test]
fn codebook_layout_and_both_index_modes() {
    let c = Codebook::new(2, 2, 2, vec![0., 1., 2., 3., 10., 11., 12., 13.]).unwrap();
    assert_eq!(c.code_space(), 4);
    let a = c.decode_overall(2, 2, &[0, 1, 2, 3]).unwrap();
    let b = c.decode_heads(2, 2, &[0, 0, 1, 0, 0, 1, 1, 1]).unwrap();
    assert_eq!(a.data(), b.data());
    assert_eq!(
        a.data(),
        &[0., 1., 10., 11., 2., 3., 10., 11., 0., 1., 12., 13., 2., 3., 12., 13.]
    );
}
#[test]
fn g1_dimensions_and_boundaries() {
    let c = Codebook::new(8, 10, 32, vec![1.; 2560]).unwrap();
    assert_eq!(c.code_space(), 100_000_000);
    assert_eq!(
        c.decode_overall(1, 2, &[0, 99_999_999]).unwrap().shape(),
        (2, 256)
    );
    assert!(matches!(
        c.decode_overall(1, 1, &[100_000_000]),
        Err(Error::Index)
    ));
    assert!(matches!(c.decode_heads(1, 1, &[10; 8]), Err(Error::Index)));
    assert!(matches!(c.decode_heads(1, 1, &[0; 7]), Err(Error::Shape)));
    assert!(matches!(c.decode_overall(0, 1, &[]), Err(Error::Shape)));
    assert!(Codebook::new(65, 2, 1, vec![0.; 130]).is_err());
    assert!(Codebook::new(1, 1, 1, vec![f32::INFINITY]).is_err());
}
